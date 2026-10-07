"""The seeded demo pipeline routes calls to three MCP servers over two transports."""

from __future__ import annotations

from sqlalchemy import select

from app.core.enums import ApprovalKind, ExecutionStatus, NodeStatus, ToolCallStatus
from app.db.session import session_scope
from app.models import ExecutionNode, LLMUsage
from app.services.context import AuthContext
from tests.conftest import RunnerFactory
from tests.helpers import SUBMIT, db_execution, pending_approval, start_demo, statuses, tool_calls


async def test_demo_pipeline_pauses_for_review_using_all_servers(
    operator_ctx: AuthContext,
    runners: RunnerFactory,
) -> None:
    execution_id = await start_demo(operator_ctx)
    assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review

    calls = await tool_calls(execution_id)
    by_tool = statuses(calls)
    # streamable_http (jobs) + stdio (calendar, github)
    assert by_tool["demo_jobs__search_jobs"] == [ToolCallStatus.completed]
    assert by_tool["demo_calendar__check_availability"] == [ToolCallStatus.completed] * 2  # map over 2 jobs
    assert by_tool["demo_github__list_repositories"] == [ToolCallStatus.completed] * 2
    assert by_tool["demo_jobs__get_job"] == [ToolCallStatus.completed]
    assert by_tool[SUBMIT] == [ToolCallStatus.awaiting_approval]
    servers = {c.server_id for c in calls}
    assert len(servers) == 3

    # Read-only calls never need approval; the destructive one does.
    approval = await pending_approval(execution_id, ApprovalKind.tool_call)
    submit = next(c for c in calls if c.namespaced_name == SUBMIT)
    assert approval.tool_call_id == submit.id
    assert approval.original_arguments == submit.arguments
    assert approval.risk_level == "high"
    assert all(
        c.policy_decision and c.policy_decision["decision"] == "allow" for c in calls if c.namespaced_name != SUBMIT
    )

    # Idempotency keys are deterministic per (execution, node, position).
    assert {c.idempotency_key for c in calls} == {f"{execution_id}:{c.node_id}:{c.call_seq}" for c in calls}

    async with session_scope() as session:
        nodes = {
            n.node_id: n.status
            for n in (
                await session.scalars(select(ExecutionNode).where(ExecutionNode.execution_id == execution_id))
            ).all()
        }
        models = set((await session.scalars(select(LLMUsage.model).where(LLMUsage.execution_id == execution_id))).all())
    assert nodes["search_jobs"] == NodeStatus.completed
    assert nodes["has_fit"] == NodeStatus.completed
    assert nodes["draft"] == NodeStatus.running
    assert models == {"fake-filter", "fake-writer"}  # two models
    assert (await db_execution(execution_id)).status == ExecutionStatus.paused_for_review
