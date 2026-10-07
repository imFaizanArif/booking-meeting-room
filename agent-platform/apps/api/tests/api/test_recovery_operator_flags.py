"""Recovery honours the operator's destructive flag even on a tool the server hints is read-only.

`readOnlyHint` is only a hint; an operator who marks a tool destructive is saying "never run this
twice without me". A worker that dies mid-call must then produce OUTCOME_UNKNOWN, not a silent re-run.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import sqlalchemy as sa

from app.core.enums import ApprovalKind, EventType, ExecutionStatus, ToolCallStatus
from app.core.time import utcnow
from app.db.session import session_scope
from app.models import Execution, ExecutionEvent, ToolCall
from app.scheduler.sweeps import recover_stale_executions
from app.services.context import AuthContext
from tests.api.conftest import Login
from tests.conftest import FakeQueue, RunnerFactory
from tests.helpers import pending_approval, tool_calls

V1 = "/api/v1"
GET_JOB = "demo_jobs__get_job"


def _graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "trigger", "name": "Start", "config": {}},
            {
                "id": "fetch",
                "type": "mcp_tool",
                "name": "Fetch",
                "error_policy": {"mode": "fail"},
                "config": {"tool": GET_JOB, "arguments": {"job_id": "job-101"}},
            },
            {"id": "end", "type": "end", "name": "End", "config": {"output": "=nodes.fetch.output"}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger", "target": "fetch"},
            {"id": "e2", "source": "fetch", "target": "end"},
        ],
    }


async def _executing_events(call_id: uuid.UUID) -> int:
    async with session_scope() as session:
        return int(
            await session.scalar(
                sa.select(sa.func.count())
                .select_from(ExecutionEvent)
                .where(ExecutionEvent.tool_call_id == call_id, ExecutionEvent.type == EventType.tool_executing)
            )
            or 0
        )


async def test_read_only_tool_marked_destructive_is_never_rerun_after_a_crash(
    login: Login,
    operator_ctx: AuthContext,
    runners: RunnerFactory,
    fake_queue: FakeQueue,
) -> None:
    operator = await login("operator@example.com")
    tools = (await operator.get(f"{V1}/mcp/tools")).json()
    tool = next(t for t in tools if t["namespaced_name"] == GET_JOB)
    assert tool["is_read_only"] is True
    marked = await operator.patch(f"{V1}/mcp/tools/{tool['id']}", json={"is_destructive": True})
    assert marked.status_code == 200 and marked.json()["is_destructive"] is True
    try:
        created = await operator.post(
            f"{V1}/pipelines", json={"name": f"Flagged {uuid.uuid4().hex[:6]}", "graph": _graph()}
        )
        assert created.status_code == 201, created.text
        started = await operator.post(f"{V1}/pipelines/{created.json()['id']}/run", json={"input": {}})
        execution_id = uuid.UUID(started.json()["id"])
        assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review
        gate = await pending_approval(execution_id)
        assert gate.reasons == ["Tool is marked destructive"]
        decided = await operator.post(f"{V1}/approvals/{gate.id}/decision", json={"action": "approve"})
        assert decided.status_code == 200

        # The worker that picked up the resume dies while the call is in flight.
        [call] = await tool_calls(execution_id)
        async with session_scope() as session:
            await session.execute(
                sa.update(ToolCall)
                .where(ToolCall.id == call.id)
                .values(status=ToolCallStatus.executing, attempt=1, started_at=utcnow())
            )
            await session.execute(
                sa.update(Execution)
                .where(Execution.id == execution_id)
                .values(
                    status=ExecutionStatus.running,
                    lease_owner="dead-worker",
                    lease_expires_at=utcnow() - timedelta(minutes=1),
                )
            )
        fake_queue.clear()
        assert await recover_stale_executions(fake_queue) == 1
        [call] = await tool_calls(execution_id)
        assert call.status == ToolCallStatus.outcome_unknown

        # Resuming asks a human; neither another worker nor another sweep calls the tool again.
        assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review
        review = await pending_approval(execution_id, ApprovalKind.outcome_unknown)
        assert review.tool_call_id == call.id
        assert await runners.new().run(execution_id) is None
        assert await recover_stale_executions(fake_queue) == 0
        [call] = await tool_calls(execution_id)
        assert call.attempt == 1 and call.status == ToolCallStatus.outcome_unknown
        assert await _executing_events(call.id) == 0

        resolved = await operator.post(f"{V1}/approvals/{review.id}/decision", json={"action": "mark_failed"})
        assert resolved.status_code == 200, resolved.text
        assert await runners.new().run(execution_id) == ExecutionStatus.failed
        [call] = await tool_calls(execution_id)
        assert call.attempt == 1 and call.status == ToolCallStatus.failed
        assert await _executing_events(call.id) == 0
    finally:
        await operator.patch(f"{V1}/mcp/tools/{tool['id']}", json={"is_destructive": False})
