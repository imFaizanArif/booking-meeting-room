"""Read-model writes (ADR 0005): execution status, node rows and their events.

All status changes use compare-and-set against the allowed source states.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert

from app.core.enums import EventType, ExecutionStatus, NodeStatus, NodeType
from app.core.errors import IllegalTransition
from app.core.redaction import redactor
from app.core.time import utcnow
from app.db.session import session_scope
from app.events.publisher import publish_execution_event
from app.models import Execution, ExecutionNode
from app.orchestration.state_machine import sources_for

_STATUS_EVENTS: dict[ExecutionStatus, EventType] = {
    ExecutionStatus.running: EventType.execution_started,
    ExecutionStatus.paused_for_review: EventType.execution_paused,
    ExecutionStatus.paused: EventType.execution_paused,
    ExecutionStatus.waiting_for_timer: EventType.execution_paused,
    ExecutionStatus.resuming: EventType.execution_resumed,
    ExecutionStatus.completed: EventType.execution_completed,
    ExecutionStatus.failed: EventType.execution_failed,
    ExecutionStatus.cancelled: EventType.execution_cancelled,
}
_TERMINALISH = {ExecutionStatus.completed, ExecutionStatus.failed, ExecutionStatus.cancelled}


def summarize(value: Any, limit: int = 4000) -> dict[str, Any] | None:
    """Bounded, redacted summary of a node input/output for the UI."""
    if value is None:
        return None
    import json

    text = json.dumps(redactor.redact(value), default=str)
    if len(text) <= limit:
        return {"value": json.loads(text)}
    return {"preview": text[:limit], "truncated": True, "size": len(text)}


async def set_execution_status(
    execution_id: uuid.UUID,
    workspace_id: uuid.UUID,
    new: ExecutionStatus,
    *,
    error: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    extra: dict[str, Any] | None = None,
    event_payload: dict[str, Any] | None = None,
    publish: bool = True,
) -> bool:
    values: dict[str, Any] = {"status": new, **(extra or {})}
    now = utcnow()
    if new == ExecutionStatus.running:
        values["started_at"] = sa.func.coalesce(Execution.started_at, now)
    if new in _TERMINALISH:
        values["finished_at"] = now
        values["lease_owner"] = None
        values["lease_expires_at"] = None
    if error is not None:
        values["error"] = redactor.redact(error)
    if output is not None:
        values["output"] = redactor.redact(output)
    async with session_scope() as session:
        changed = await session.scalar(
            sa.update(Execution)
            .where(Execution.id == execution_id, Execution.status.in_(sources_for(new)))
            .values(**values)
            .returning(Execution.id)
        )
    if changed is None:
        return False
    event = _STATUS_EVENTS.get(new)
    if publish and event is not None:
        payload = {"status": new.value, **(event_payload or {})}
        if error:
            payload["error"] = error
        await publish_execution_event(workspace_id=workspace_id, execution_id=execution_id, type=event, payload=payload)
    return True


async def require_execution_status(
    execution_id: uuid.UUID, workspace_id: uuid.UUID, new: ExecutionStatus, **kwargs: Any
) -> None:
    if not await set_execution_status(execution_id, workspace_id, new, **kwargs):
        raise IllegalTransition(f"Execution could not move to {new.value}", details={"to": new.value})


async def upsert_node(
    execution_id: uuid.UUID,
    node_id: str,
    node_type: NodeType,
    name: str,
    status: NodeStatus,
    **values: Any,
) -> None:
    now = utcnow()
    row = {
        "execution_id": execution_id,
        "node_id": node_id,
        "node_type": node_type,
        "name": name,
        "status": status,
        **values,
    }
    if status == NodeStatus.running:
        row.setdefault("started_at", now)
    if status in (NodeStatus.completed, NodeStatus.failed, NodeStatus.skipped, NodeStatus.cancelled):
        row.setdefault("finished_at", now)
    update_cols = {k: v for k, v in row.items() if k not in ("execution_id", "node_id")}
    if "started_at" in update_cols:
        update_cols["started_at"] = sa.func.coalesce(ExecutionNode.started_at, update_cols["started_at"])
    async with session_scope() as session:
        stmt = insert(ExecutionNode).values(id=uuid.uuid4(), **row)
        stmt = stmt.on_conflict_do_update(index_elements=["execution_id", "node_id"], set_=update_cols)
        await session.execute(stmt)


async def node_event(
    workspace_id: uuid.UUID, execution_id: uuid.UUID, type: EventType, node_id: str, payload: dict[str, Any]
) -> None:
    await publish_execution_event(
        workspace_id=workspace_id, execution_id=execution_id, type=type, node_id=node_id, payload=payload
    )
