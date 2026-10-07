"""Persist-then-publish for execution events with a gap-free per-execution sequence."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa

from app.core.enums import EventType
from app.core.logging import get_logger
from app.core.redaction import redactor
from app.core.time import utcnow
from app.db.session import session_scope
from app.events.bus import get_event_bus
from app.events.schemas import ExecutionEventOut, execution_channel, workspace_channel
from app.models import Execution, ExecutionEvent

log = get_logger(__name__)

# Execution-level events also go to the workspace stream (dashboard, approvals desk).
_WORKSPACE_FANOUT = frozenset(
    {
        EventType.execution_created,
        EventType.execution_started,
        EventType.execution_paused,
        EventType.execution_resumed,
        EventType.execution_completed,
        EventType.execution_failed,
        EventType.execution_cancelled,
        EventType.approval_created,
        EventType.approval_decided,
    }
)


async def publish_execution_event(
    *,
    workspace_id: uuid.UUID,
    execution_id: uuid.UUID,
    type: EventType,
    node_id: str | None = None,
    tool_call_id: uuid.UUID | None = None,
    approval_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> ExecutionEventOut:
    clean = redactor.redact(payload or {})
    async with session_scope() as session:
        seq = await session.scalar(
            sa.update(Execution)
            .where(Execution.id == execution_id)
            .values(last_event_seq=Execution.last_event_seq + 1)
            .returning(Execution.last_event_seq)
        )
        if seq is None:
            raise LookupError(f"execution {execution_id} not found")
        row = ExecutionEvent(
            workspace_id=workspace_id,
            execution_id=execution_id,
            seq=seq,
            type=type,
            node_id=node_id,
            tool_call_id=tool_call_id,
            approval_id=approval_id,
            payload=clean,
            created_at=utcnow(),
        )
        session.add(row)
        await session.flush()
        out = ExecutionEventOut.model_validate(row, from_attributes=True)
    message = out.model_dump(mode="json")
    bus = get_event_bus()
    try:
        await bus.publish(execution_channel(execution_id), message)
        if type in _WORKSPACE_FANOUT:
            await bus.publish(
                workspace_channel(workspace_id),
                {
                    "type": type.value,
                    "execution_id": str(execution_id),
                    "approval_id": str(approval_id) if approval_id else None,
                    "payload": clean,
                    "at": message["created_at"],
                },
            )
    except Exception as exc:  # pub/sub loss is tolerated; clients replay from Postgres
        log.warning("event_publish_failed", error=str(exc), event_type=type.value)
    return out


async def publish_workspace_event(
    workspace_id: uuid.UUID,
    type: EventType,
    *,
    server_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    message = {
        "type": type.value,
        "server_id": str(server_id) if server_id else None,
        "payload": redactor.redact(payload or {}),
        "at": utcnow().isoformat(),
    }
    try:
        await get_event_bus().publish(workspace_channel(workspace_id), message)
    except Exception as exc:
        log.warning("event_publish_failed", error=str(exc), event_type=type.value)
