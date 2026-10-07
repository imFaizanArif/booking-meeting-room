"""Approval pause survives a worker restart; the side effect happens exactly once."""

from __future__ import annotations

from typing import Any

from mock_mcp.common import effects

from app.core.enums import ApprovalStatus, DecisionAction, ExecutionStatus, ToolCallStatus
from app.services.context import AuthContext
from app.workers.queue import Job
from tests.conftest import FakeQueue, RunnerFactory
from tests.helpers import SUBMIT, approvals, db_execution, decide_as, pending_approval, start_demo, submit_calls


async def test_pause_restart_approve_executes_once(
    operator_ctx: AuthContext, runners: RunnerFactory, fake_queue: FakeQueue, checkpointer: Any,
) -> None:
    execution_id = await start_demo(operator_ctx)
    assert fake_queue.of(Job.run_execution) == [(str(execution_id),)]

    first_worker = runners.new()
    assert await first_worker.run(execution_id) == ExecutionStatus.paused_for_review
    row = await db_execution(execution_id)
    assert row.lease_owner is None, "a paused execution must not hold a worker lease"
    approval = await pending_approval(execution_id)
    [call] = await submit_calls(execution_id)
    assert call.status == ToolCallStatus.awaiting_approval
    assert effects("jobs") == []

    # The worker process dies while the execution waits for review.
    await first_worker.connections.shutdown()

    await decide_as(operator_ctx, approval.id, DecisionAction.approve)
    assert (await db_execution(execution_id)).status == ExecutionStatus.resuming
    assert fake_queue.of(Job.resume_execution)[-1] == (str(execution_id),)

    second_worker = runners.new()
    assert await second_worker.run(execution_id) == ExecutionStatus.completed

    row = await db_execution(execution_id)
    assert row.output is not None and "Submitted proposal prop-" in row.output["proposal"]["text"]
    [call] = await submit_calls(execution_id)
    assert call.status == ToolCallStatus.completed
    assert [a.status for a in await approvals(execution_id)] == [ApprovalStatus.approved]
    submitted = effects("jobs")
    assert len(submitted) == 1
    assert submitted[0]["result"]["job_id"] == call.arguments["job_id"]

    # A duplicate resume job (e.g. redelivered by the queue) does nothing.
    third_worker = runners.new()
    assert await third_worker.run(execution_id) is None
    assert len(effects("jobs")) == 1
    assert call.namespaced_name == SUBMIT

