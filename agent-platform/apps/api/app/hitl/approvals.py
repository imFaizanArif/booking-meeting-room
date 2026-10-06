"""Approval records: creation (worker side) and decisions (API side).

Integrity: decisions lock the approval row (`SELECT ... FOR UPDATE`) and only accept
`pending`, so double clicks and concurrent reviewers cannot both win.
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit
from app.core.enums import (
    ApprovalKind,
    ApprovalStatus,
    AuditEventType,
    DecisionAction,
    ErrorCode,
    EventType,
    ExecutionStatus,
    Role,
    ToolCallStatus,
)
from app.core.errors import AppError, NotFound, ValidationFailed
from app.core.redaction import redactor
from app.core.time import utcnow
from app.events.publisher import publish_execution_event
from app.models import Approval, Execution, ToolCall
from app.orchestration.snapshot import ConfigSnapshot
from app.services.context import AuthContext
from app.tools.validation import argument_errors
from app.workers.queue import Job, get_queue, resume_job_id

_TOOL_ACTIONS = {DecisionAction.approve, DecisionAction.edit, DecisionAction.reject, DecisionAction.regenerate}
_OUTCOME_ACTIONS = {DecisionAction.mark_succeeded, DecisionAction.mark_failed, DecisionAction.rerun}
_DATA_ACTIONS = {DecisionAction.approve, DecisionAction.edit, DecisionAction.reject}


class ApprovalAlreadyDecided(AppError):
    code = ErrorCode.approval_already_decided


async def approvals_for_tool_call(session: AsyncSession, tool_call_id: uuid.UUID) -> list[Approval]:
    return list((await session.scalars(
        select(Approval).where(Approval.tool_call_id == tool_call_id).order_by(Approval.created_at, Approval.id)
    )).all())


async def create_approval(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    execution_id: uuid.UUID,
    node_id: str,
    kind: ApprovalKind,
    title: str,
    summary: str | None,
    tool_call_id: uuid.UUID | None = None,
    risk_level: str | None = None,
    reasons: list[str] | None = None,
    original_arguments: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
    expires_in_minutes: int | None = None,
    supersedes: uuid.UUID | None = None,
) -> Approval:
    approval = Approval(
        id=uuid.uuid4(), workspace_id=workspace_id, execution_id=execution_id, node_id=node_id, kind=kind,
        tool_call_id=tool_call_id, status=ApprovalStatus.pending, title=title[:300], summary=summary,
        risk_level=risk_level, reasons=reasons or [], original_arguments=original_arguments,
        payload=redactor.redact(payload) if payload else None,
        expires_at=utcnow() + timedelta(minutes=expires_in_minutes) if expires_in_minutes else None,
    )
    session.add(approval)
    await session.flush()
    if supersedes is not None:
        await session.execute(
            sa.update(Approval).where(Approval.id == supersedes).values(superseded_by=approval.id)
        )
    return approval


def _allowed_actions(kind: ApprovalKind) -> set[DecisionAction]:
    if kind == ApprovalKind.tool_call:
        return _TOOL_ACTIONS
    if kind == ApprovalKind.outcome_unknown:
        return _OUTCOME_ACTIONS
    return _DATA_ACTIONS


async def decide(
    session: AsyncSession,
    ctx: AuthContext,
    approval_id: uuid.UUID,
    *,
    action: DecisionAction,
    edited_arguments: dict[str, Any] | None = None,
    edited_data: Any = None,
    reason: str | None = None,
    feedback: str | None = None,
    result: Any = None,
    confirm: bool = False,
) -> Approval:
    ctx.require(Role.operator)
    approval = await session.scalar(
        select(Approval).where(Approval.id == approval_id, Approval.workspace_id == ctx.workspace_id)
        .with_for_update()
    )
    if approval is None:
        raise NotFound("Approval not found")
    if approval.status != ApprovalStatus.pending:
        raise ApprovalAlreadyDecided(
            f"This approval was already {approval.status.value}",
            details={"status": approval.status.value, "decided_by": str(approval.decided_by) if approval.decided_by else None},
        )
    if approval.expires_at is not None and approval.expires_at < utcnow():
        raise ApprovalAlreadyDecided("This approval has expired", details={"status": "expired"})
    if action not in _allowed_actions(approval.kind):
        raise ValidationFailed(f"{action.value} is not valid for a {approval.kind.value} approval")

    execution = await session.get(Execution, approval.execution_id)
    assert execution is not None
    tool_call = await session.get(ToolCall, approval.tool_call_id) if approval.tool_call_id else None
    diff: dict[str, Any] | None = None
    now = utcnow()

    if action == DecisionAction.edit:
        if approval.kind == ApprovalKind.tool_call:
            if not isinstance(edited_arguments, dict):
                raise ValidationFailed("edited_arguments must be a JSON object",
                                       details={"fields": [{"field": "", "message": "Expected an object"}]})
            snapshot = ConfigSnapshot.model_validate(execution.config_snapshot)
            tool = snapshot.tools.get(tool_call.namespaced_name) if tool_call else None
            if tool is None:
                raise ValidationFailed("The tool is no longer part of this execution's snapshot")
            errors = argument_errors(tool.input_schema, edited_arguments)
            if errors:
                raise ValidationFailed("Edited arguments do not match the tool schema", details={"fields": errors})
            diff = _arg_diff(approval.original_arguments or {}, edited_arguments)
            approval.edited_arguments = edited_arguments
        else:
            approval.resolution = {"edited_data": edited_data}
        approval.status = ApprovalStatus.approved
    elif action == DecisionAction.approve:
        approval.status = ApprovalStatus.approved
    elif action == DecisionAction.reject:
        if not (reason or "").strip():
            raise ValidationFailed("A reason is required to reject", details={"fields": [
                {"field": "reason", "message": "Explain why so the agent can adapt"}]})
        approval.status = ApprovalStatus.rejected
    elif action == DecisionAction.regenerate:
        approval.status = ApprovalStatus.superseded
    elif action == DecisionAction.mark_succeeded:
        approval.status = ApprovalStatus.approved
        approval.resolution = {"action": action.value, "result": result}
    elif action == DecisionAction.mark_failed:
        approval.status = ApprovalStatus.approved
        approval.resolution = {"action": action.value}
    elif action == DecisionAction.rerun:
        if not confirm:
            raise ValidationFailed("Re-running a call with an unknown outcome needs explicit confirmation",
                                   details={"fields": [{"field": "confirm", "message": "Must be true"}]})
        approval.status = ApprovalStatus.approved
        approval.resolution = {"action": action.value}

    approval.decision = action.value
    approval.decided_by = ctx.user_id
    approval.decided_at = now
    approval.reason = reason
    approval.feedback = feedback
    if tool_call is not None and approval.kind == ApprovalKind.tool_call:
        if approval.status == ApprovalStatus.approved:
            tool_call.status = ToolCallStatus.approved
        elif approval.status == ApprovalStatus.rejected:
            tool_call.status = ToolCallStatus.rejected
        elif approval.status == ApprovalStatus.superseded:
            tool_call.status = ToolCallStatus.cancelled

    await audit(session, event_type=AuditEventType.approval_decided, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="approval", entity_id=approval.id, execution_id=approval.execution_id,
                payload={"action": action.value, "reason": reason, "feedback": feedback, "diff": diff,
                         "tool": tool_call.namespaced_name if tool_call else None})
    should_resume = execution.status in (ExecutionStatus.paused_for_review, ExecutionStatus.resuming,
                                         ExecutionStatus.running, ExecutionStatus.queued)
    await session.flush()
    await session.execute(
        sa.update(Execution)
        .where(Execution.id == execution.id, Execution.status == ExecutionStatus.paused_for_review)
        .values(status=ExecutionStatus.resuming)
    )
    await session.commit()

    tool_event = {
        DecisionAction.approve: EventType.tool_approved, DecisionAction.edit: EventType.tool_approved,
        DecisionAction.reject: EventType.tool_rejected, DecisionAction.regenerate: EventType.tool_rejected,
    }.get(action)
    await publish_execution_event(
        workspace_id=approval.workspace_id, execution_id=approval.execution_id, type=EventType.approval_decided,
        approval_id=approval.id, node_id=approval.node_id,
        payload={"action": action.value, "decided_by": ctx.email, "reason": reason, "diff": diff},
    )
    if tool_event is not None and tool_call is not None:
        await publish_execution_event(
            workspace_id=approval.workspace_id, execution_id=approval.execution_id, type=tool_event,
            tool_call_id=tool_call.id, node_id=approval.node_id, payload={"tool": tool_call.namespaced_name},
        )
    if should_resume:
        await get_queue().enqueue(Job.resume_execution, str(approval.execution_id),
                                  job_id=resume_job_id(approval.execution_id))
    return approval


def _arg_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes[key] = {"from": before.get(key), "to": after.get(key)}
    return redactor.redact(changes)
