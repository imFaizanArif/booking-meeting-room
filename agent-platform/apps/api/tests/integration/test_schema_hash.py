"""Tool schema drift between snapshot and live server fails the call with TOOL_SCHEMA_CHANGED."""

from __future__ import annotations

from mock_mcp.common import effects

from app.core.enums import DecisionAction, ErrorCode, ExecutionStatus, ToolCallStatus
from app.services.context import AuthContext
from tests.conftest import RunnerFactory
from tests.helpers import (
    SUBMIT,
    db_execution,
    decide_as,
    patch_snapshot_tool,
    pending_approval,
    start_demo,
    submit_calls,
    tool_calls,
)


async def test_policy_denies_call_when_live_schema_differs(operator_ctx: AuthContext, runners: RunnerFactory) -> None:
    execution_id = await start_demo(operator_ctx)
    await patch_snapshot_tool(execution_id, "demo_jobs__search_jobs", schema_hash="0" * 64)

    assert await runners.new().run(execution_id) == ExecutionStatus.failed
    [call] = await tool_calls(execution_id)
    assert call.namespaced_name == "demo_jobs__search_jobs"
    assert call.status == ToolCallStatus.rejected
    assert call.error is not None and call.error["code"] == ErrorCode.tool_schema_changed.value
    assert call.policy_decision is not None and call.policy_decision["code"] == ErrorCode.tool_schema_changed.value
    row = await db_execution(execution_id)
    assert row.error is not None and row.error["code"] == ErrorCode.tool_schema_changed.value


async def test_schema_change_after_approval_blocks_execution(
    operator_ctx: AuthContext,
    runners: RunnerFactory,
) -> None:
    execution_id = await start_demo(operator_ctx)
    assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review
    approval = await pending_approval(execution_id)
    # The server changed the tool while the approval was waiting.
    await patch_snapshot_tool(execution_id, SUBMIT, schema_hash="f" * 64)
    await decide_as(operator_ctx, approval.id, DecisionAction.approve)

    assert await runners.new().run(execution_id) == ExecutionStatus.completed  # the agent sees a failed call
    [call] = await submit_calls(execution_id)
    assert call.status == ToolCallStatus.failed
    assert call.error is not None and call.error["code"] == ErrorCode.tool_schema_changed.value
    assert effects("jobs") == []
