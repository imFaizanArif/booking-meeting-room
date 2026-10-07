"""Deterministic nodes: trigger, condition, transform, end, notification, delay, human approval."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.enums import ApprovalKind, ApprovalStatus, ErrorCode, EventType, InterruptKind
from app.core.errors import AppError
from app.core.time import utcnow
from app.db.session import session_scope
from app.events.publisher import publish_execution_event
from app.hitl.approvals import create_approval
from app.models import Approval, DurableTimer
from app.notifications.dispatcher import NotificationMessage
from app.orchestration.expressions import evaluate, jsonpath, resolve
from app.orchestration.runtime import RuntimeContext
from app.orchestration.state import GraphState
from app.prompts.render import render
from app.schemas.pipeline_graph import (
    ConditionNode,
    DelayNode,
    EndNode,
    HumanApprovalNode,
    NotificationNode,
    TransformMode,
    TransformNode,
    TriggerNode,
)
from app.tools.validation import argument_errors
from app.workers.queue import Job


class TriggerExecutor:
    async def run(self, node: TriggerNode, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> Any:
        data = state.get("input") or {}
        errors = argument_errors(node.config.input_schema, data)
        if errors:
            raise AppError(
                "Pipeline input does not match the trigger schema",
                code=ErrorCode.validation_error,
                details={"fields": errors},
            )
        return data


class ConditionExecutor:
    async def run(self, node: ConditionNode, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> Any:
        value = evaluate(node.config.expression, rt.names(state, extra))
        return {"result": bool(value), "value": value}


class TransformExecutor:
    async def run(self, node: TransformNode, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> Any:
        cfg = node.config
        names = rt.names(state, extra)
        if cfg.mode == TransformMode.expression:
            if not cfg.expression:
                raise AppError("Transform expression is empty", code=ErrorCode.expression_error)
            return evaluate(cfg.expression, names)
        if cfg.mode == TransformMode.jsonpath:
            if not cfg.jsonpath:
                raise AppError("JSONPath is empty", code=ErrorCode.expression_error)
            document = evaluate(cfg.source, names) if cfg.source else names
            return jsonpath(document, cfg.jsonpath)
        return resolve(cfg.template or {}, names)


class EndExecutor:
    async def run(self, node: EndNode, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> Any:
        return resolve(node.config.output, rt.names(state, extra))


class NotificationExecutor:
    async def run(self, node: NotificationNode, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> Any:
        text = render(node.config.message, rt.template_context(state, extra)) if node.config.message else node.name
        delivered = await rt.notifications.send(
            rt.workspace_id,
            NotificationMessage(
                event="pipeline.notification",
                title=f"{rt.snapshot.pipeline_name}: {node.name}",
                text=text,
                fields={"execution": str(rt.execution_id)},
            ),
            channel_ids=list(node.config.channel_ids) or None,
        )
        return {"delivered": delivered, "text": text}


class DelayExecutor:
    """Durable timer: the worker is released; the scheduler resumes the execution when due."""

    async def run(self, node: DelayNode, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> Any:
        async with session_scope() as session:
            timer = await session.scalar(
                select(DurableTimer).where(
                    DurableTimer.execution_id == rt.execution_id, DurableTimer.node_id == node.id
                )
            )
            if timer is None:
                wake_at = self._wake_at(node, rt, state, extra)
                await session.execute(
                    insert(DurableTimer)
                    .values(
                        execution_id=rt.execution_id,
                        node_id=node.id,
                        wake_at=wake_at,
                    )
                    .on_conflict_do_nothing()
                )
                timer = await session.scalar(
                    select(DurableTimer).where(
                        DurableTimer.execution_id == rt.execution_id, DurableTimer.node_id == node.id
                    )
                )
            assert timer is not None
            wake_at = timer.wake_at
        if wake_at > utcnow():
            if rt.queue is not None:
                await rt.queue.enqueue(
                    Job.resume_execution, str(rt.execution_id), job_id=f"timer:{timer.id}", defer_until=wake_at
                )
            interrupt({"kind": InterruptKind.timer.value, "node_id": node.id, "wake_at": wake_at.isoformat()})
        return {"waited_until": wake_at.isoformat()}

    @staticmethod
    def _wake_at(node: DelayNode, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> datetime:
        if node.config.until:
            value = evaluate(node.config.until, rt.names(state, extra))
            try:
                wake = datetime.fromisoformat(str(value))
            except ValueError as exc:
                raise AppError(
                    f"Delay 'until' is not an ISO datetime: {value!r}", code=ErrorCode.expression_error
                ) from exc
            return wake if wake.tzinfo else wake.replace(tzinfo=utcnow().tzinfo)
        return utcnow() + timedelta(seconds=node.config.seconds or 0)


class HumanApprovalExecutor:
    async def run(self, node: HumanApprovalNode, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> Any:
        data = resolve(node.config.data, rt.names(state, extra))
        async with session_scope() as session:
            approvals = list(
                (
                    await session.scalars(
                        select(Approval)
                        .where(
                            Approval.execution_id == rt.execution_id,
                            Approval.node_id == node.id,
                            Approval.kind == ApprovalKind.data_review,
                        )
                        .order_by(Approval.created_at, Approval.id)
                    )
                ).all()
            )
            if not approvals:
                approval = await create_approval(
                    session,
                    workspace_id=rt.workspace_id,
                    execution_id=rt.execution_id,
                    node_id=node.id,
                    kind=ApprovalKind.data_review,
                    title=node.config.title,
                    summary=node.config.instructions or None,
                    risk_level="medium",
                    reasons=["Pipeline step requires human review"],
                    payload={"data": data, "allow_edit": node.config.allow_edit},
                    expires_in_minutes=node.config.expires_in_minutes,
                )
                approvals = [approval]
                created = approval
            else:
                created = None
        if created is not None:
            await publish_execution_event(
                workspace_id=rt.workspace_id,
                execution_id=rt.execution_id,
                type=EventType.approval_created,
                node_id=node.id,
                approval_id=created.id,
                payload={"title": created.title, "kind": "data_review"},
            )
            if rt.queue is not None:
                await rt.queue.enqueue(Job.send_notification, str(created.id), job_id=f"notify:{created.id}")
        for approval in approvals:
            interrupt({"kind": InterruptKind.approval.value, "approval_id": str(approval.id), "node_id": node.id})
        async with session_scope() as session:
            decided = await session.get(Approval, approvals[-1].id, populate_existing=True)
        assert decided is not None
        edited = (decided.resolution or {}).get("edited_data")
        return {
            "approved": decided.status == ApprovalStatus.approved,
            "status": decided.status.value,
            "data": edited if edited is not None else data,
            "edited": edited is not None,
            "reason": decided.reason,
            "decided_by": str(decided.decided_by) if decided.decided_by else None,
        }
