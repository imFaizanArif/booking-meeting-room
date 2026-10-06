"""Append-only audit writer. Payloads are redacted before insert."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AuditEventType
from app.core.logging import current_context
from app.core.redaction import redactor
from app.models import AuditEvent
from app.services.context import Actor, AuthContext


async def audit(
    session: AsyncSession,
    *,
    event_type: AuditEventType,
    actor: Actor | AuthContext,
    workspace_id: uuid.UUID | None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | str | None = None,
    execution_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    ip = actor.ip if isinstance(actor, AuthContext) else None
    request_id = actor.request_id if isinstance(actor, AuthContext) else None
    resolved = actor.actor if isinstance(actor, AuthContext) else actor
    session.add(
        AuditEvent(
            workspace_id=workspace_id,
            actor_type=resolved.type,
            actor_id=resolved.id,
            actor_label=resolved.label,
            event_type=event_type.value,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            execution_id=execution_id,
            payload=redactor.redact(payload or {}),
            request_id=request_id or current_context().get("request_id"),
            ip=ip,
        )
    )


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Shallow field diff for config-change audit entries."""
    changes: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            changes[key] = {"from": before.get(key), "to": after.get(key)}
    return changes
