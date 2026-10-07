"""Edit / reject / regenerate decisions and how they shape the agent's history."""

from __future__ import annotations

import json
from typing import Any

from mock_mcp.common import effects

from app.core.enums import ApprovalStatus, DecisionAction, ExecutionStatus, ToolCallStatus
from app.services.context import AuthContext
from tests.conftest import RunnerFactory
from tests.helpers import (
    SUBMIT,
    approvals,
    db_execution,
    decide_as,
    graph_values,
    pending_approval,
    start_demo,
    submit_calls,
)

EDITED = {
    "job_id": "job-101",
    "hourly_rate": 99,
    "cover_letter": "Edited by the reviewer: concise, specific and with the right rate.",
}


def _assistant_submit_calls(values: dict[str, Any]) -> list[dict[str, Any]]:
    messages = values["agents"]["draft"]["messages"]
    return [call for m in messages if m["role"] == "assistant" for call in m["tool_calls"] if call["name"] == SUBMIT]


def _tool_results(values: dict[str, Any]) -> list[dict[str, Any]]:
    return [m for m in values["agents"]["draft"]["messages"] if m["role"] == "tool" and m["name"] == SUBMIT]


async def test_edit_then_approve_rewrites_history(
    operator_ctx: AuthContext,
    runners: RunnerFactory,
    checkpointer: Any,
) -> None:
    execution_id = await start_demo(operator_ctx)
    assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review
    approval = await pending_approval(execution_id)
    original = dict(approval.original_arguments or {})
    assert original != EDITED

    await decide_as(operator_ctx, approval.id, DecisionAction.edit, edited_arguments=EDITED)
    assert await runners.new().run(execution_id) == ExecutionStatus.completed

    values = await graph_values(checkpointer, execution_id)
    [proposed] = _assistant_submit_calls(values)
    assert proposed["arguments"] == EDITED  # the model's own message now shows what actually ran
    [decided] = await approvals(execution_id)
    assert decided.status == ApprovalStatus.approved and decided.decision == "edit"
    assert decided.original_arguments == original
    assert decided.edited_arguments == EDITED
    [call] = await submit_calls(execution_id)
    assert call.arguments == EDITED and call.status == ToolCallStatus.completed
    [effect] = effects("jobs")
    assert effect["result"]["hourly_rate"] == 99
    assert values["agents"]["draft"]["actions"][-1]["edited"] is True


async def test_edit_with_invalid_arguments_is_refused(operator_ctx: AuthContext, runners: RunnerFactory) -> None:
    from app.core.errors import ValidationFailed

    execution_id = await start_demo(operator_ctx)
    await runners.new().run(execution_id)
    approval = await pending_approval(execution_id)
    try:
        await decide_as(
            operator_ctx,
            approval.id,
            DecisionAction.edit,
            edited_arguments={"job_id": "job-101", "hourly_rate": "lots"},
        )
    except ValidationFailed as exc:
        fields = {f["field"] for f in exc.details["fields"]}
        assert {"hourly_rate", "cover_letter"} <= fields
    else:
        raise AssertionError("invalid edit accepted")
    assert (await pending_approval(execution_id)).id == approval.id


async def test_reject_returns_structured_result_and_never_executes(
    operator_ctx: AuthContext,
    runners: RunnerFactory,
    checkpointer: Any,
) -> None:
    execution_id = await start_demo(operator_ctx)
    await runners.new().run(execution_id)
    approval = await pending_approval(execution_id)

    await decide_as(operator_ctx, approval.id, DecisionAction.reject, reason="Rate is too low for this client")
    assert await runners.new().run(execution_id) == ExecutionStatus.completed

    [call] = await submit_calls(execution_id)
    assert call.status == ToolCallStatus.rejected
    assert effects("jobs") == []
    values = await graph_values(checkpointer, execution_id)
    [result] = _tool_results(values)
    body = json.loads(result["content"])
    assert result["is_error"] is True
    assert body["rejected"] is True and body["reason"] == "Rate is too low for this client"
    row = await db_execution(execution_id)
    assert row.output is not None
    assert "not submitted" in row.output["proposal"]["text"]
    assert row.output["proposal"]["stop"] == "final_answer"


async def test_regenerate_supersedes_and_second_proposal_can_be_approved(
    operator_ctx: AuthContext,
    runners: RunnerFactory,
    checkpointer: Any,
) -> None:
    execution_id = await start_demo(operator_ctx)
    await runners.new().run(execution_id)
    first = await pending_approval(execution_id)

    await decide_as(operator_ctx, first.id, DecisionAction.regenerate, feedback="Mention availability next week.")
    assert await runners.new().run(execution_id) == ExecutionStatus.paused_for_review

    second = await pending_approval(execution_id)
    assert second.id != first.id
    rows = {a.id: a for a in await approvals(execution_id)}
    assert rows[first.id].status == ApprovalStatus.superseded
    assert rows[first.id].superseded_by == second.id
    assert "Mention availability next week." in (second.original_arguments or {})["cover_letter"]
    calls = await submit_calls(execution_id)
    assert [c.status for c in calls] == [ToolCallStatus.cancelled, ToolCallStatus.awaiting_approval]
    assert effects("jobs") == []

    await decide_as(operator_ctx, second.id, DecisionAction.approve)
    assert await runners.new().run(execution_id) == ExecutionStatus.completed
    assert [c.status for c in await submit_calls(execution_id)] == [ToolCallStatus.cancelled, ToolCallStatus.completed]
    [effect] = effects("jobs")
    assert effect["result"]["status"] == "submitted"
    row = await db_execution(execution_id)
    assert row.output is not None and "Submitted revised proposal" in row.output["proposal"]["text"]

    values = await graph_values(checkpointer, execution_id)
    first_result = json.loads(_tool_results(values)[0]["content"])
    assert first_result["reviewer_requested_new_proposal"] is True
    assert first_result["feedback"] == "Mention availability next week."
