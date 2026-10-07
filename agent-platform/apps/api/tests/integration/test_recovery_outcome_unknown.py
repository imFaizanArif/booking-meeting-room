"""A worker dies mid-call on a destructive tool: never re-executed, a human resolves it."""

from __future__ import annotations

from datetime import timedelta

import sqlalchemy as sa
from mock_mcp.common import effects

from app.core.enums import (
    ApprovalKind,
    ApprovalStatus,
    DecisionAction,
    ExecutionStatus,
    ToolCallStatus,
)
from app.core.errors import ValidationFailed
from app.core.time import utcnow
from app.db.session import session_scope
from app.models import Execution, ToolCall
from app.scheduler.sweeps import recover_stale_executions
from app.services.context import AuthContext
from app.workers.queue import Job
from tests.conftest import FakeQueue, RunnerFactory
from tests.helpers import approvals, db_execution, decide_as, pending_approval, start_demo, submit_calls


async def _simulate_crash_during_submit(execution_id: object, call_id: object) -> None:
    async with session_scope() as session:
        await session.execute(sa.update(ToolCall).where(ToolCall.id == call_id).values(
            status=ToolCallStatus.executing, attempt=1, started_at=utcnow()))
        await session.execute(sa.update(Execution).where(Execution.id == execution_id).values(
            status=ExecutionStatus.running, lease_owner="dead-worker",
            lease_expires_at=utcnow() - timedelta(minutes=1)))


async def test_executing_call_becomes_outcome_unknown_and_is_not_rerun(
    operator_ctx: AuthContext, runners: RunnerFactory, fake_queue: FakeQueue,
) -> None:
    execution_id = await start_demo(operator_ctx)
    assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review
    gate = await pending_approval(execution_id)
    await decide_as(operator_ctx, gate.id, DecisionAction.approve)
    [call] = await submit_calls(execution_id)
    await _simulate_crash_during_submit(execution_id, call.id)
    fake_queue.clear()

    assert await recover_stale_executions(fake_queue) == 1
    row = await db_execution(execution_id)
    assert row.status == ExecutionStatus.queued and row.lease_owner is None
    [call] = await submit_calls(execution_id)
    assert call.status == ToolCallStatus.outcome_unknown
    assert fake_queue.of(Job.resume_execution) == [(str(execution_id),)]

    # A fresh worker resumes from the checkpoint and asks a human instead of calling again.
    assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review
    review = await pending_approval(execution_id, ApprovalKind.outcome_unknown)
    assert review.tool_call_id == call.id
    assert review.original_arguments == call.arguments
    assert effects("jobs") == []

    # Tool-call actions are not valid for an outcome review, re-run needs explicit confirmation.
    for action, kwargs in ((DecisionAction.approve, {}), (DecisionAction.rerun, {"confirm": False})):
        try:
            await decide_as(operator_ctx, review.id, action, **kwargs)
        except ValidationFailed:
            pass
        else:
            raise AssertionError(f"{action} accepted")

    await decide_as(operator_ctx, review.id, DecisionAction.mark_succeeded,
                    result={"proposal_id": "prop-confirmed-by-human"})
    assert await runners.new().run(execution_id) == ExecutionStatus.completed

    [call] = await submit_calls(execution_id)
    assert call.status == ToolCallStatus.completed
    assert call.result is not None and call.result["metadata"] == {"resolved_by_human": True}
    assert call.result["structured_content"] == {"proposal_id": "prop-confirmed-by-human"}
    assert effects("jobs") == [], "the destructive call must never be re-executed automatically"
    kinds = {(a.kind, a.status) for a in await approvals(execution_id)}
    assert kinds == {(ApprovalKind.tool_call, ApprovalStatus.approved),
                     (ApprovalKind.outcome_unknown, ApprovalStatus.approved)}
    assert "prop-confirmed-by-human" in ((await db_execution(execution_id)).output or {})["proposal"]["text"]


async def test_recovery_resets_read_only_calls_and_requeues_orphans(
    operator_ctx: AuthContext, runners: RunnerFactory, fake_queue: FakeQueue,
) -> None:
    execution_id = await start_demo(operator_ctx)
    assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review
    async with session_scope() as session:
        read_only = await session.scalar(sa.select(ToolCall).where(
            ToolCall.execution_id == execution_id, ToolCall.namespaced_name == "demo_jobs__get_job"))
        assert read_only is not None
        read_only.status = ToolCallStatus.executing
        await session.execute(sa.update(Execution).where(Execution.id == execution_id).values(
            status=ExecutionStatus.running, lease_owner="dead", lease_expires_at=utcnow() - timedelta(seconds=5)))
    fake_queue.clear()
    assert await recover_stale_executions(fake_queue) == 1
    async with session_scope() as session:
        status = await session.scalar(sa.select(ToolCall.status).where(ToolCall.id == read_only.id))
    assert status == ToolCallStatus.pending

    # A live lease is left alone.
    async with session_scope() as session:
        await session.execute(sa.update(Execution).where(Execution.id == execution_id).values(
            status=ExecutionStatus.running, lease_owner="alive", lease_expires_at=utcnow() + timedelta(minutes=1)))
    assert await recover_stale_executions(fake_queue) == 0
