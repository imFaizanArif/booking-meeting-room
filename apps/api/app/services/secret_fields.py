"""Helpers for write-only secret fields on config rows (API keys, env, headers, webhook URLs)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit
from app.core.enums import AuditEventType
from app.models import Secret
from app.schemas.common import SecretFieldState
from app.secrets.manager import get_secret_manager, parse_ref
from app.services.context import AuthContext


async def put_field(session: AsyncSession, ctx: AuthContext, name: str, value: str) -> str:
    meta = await get_secret_manager().put(session, ctx.workspace_id, name, value, managed=True)
    await audit(
        session,
        event_type=AuditEventType.secret_written,
        actor=ctx,
        workspace_id=ctx.workspace_id,
        entity_type="secret",
        entity_id=meta.id,
        payload={"name": name},
    )
    return meta.ref


async def delete_field(session: AsyncSession, ctx: AuthContext, ref: str | None) -> None:
    if not ref:
        return
    try:
        await get_secret_manager().delete(session, ctx.workspace_id, ref)
    except Exception:  # noqa: BLE001 - already gone
        return
    await audit(
        session,
        event_type=AuditEventType.secret_deleted,
        actor=ctx,
        workspace_id=ctx.workspace_id,
        entity_type="secret",
        entity_id=ref,
    )


async def update_map(
    session: AsyncSession,
    ctx: AuthContext,
    *,
    prefix: str,
    current: dict[str, Any],
    new_values: dict[str, str],
    keep: list[str],
) -> dict[str, str]:
    """Replace a name -> secret_ref map: keep listed names, write new values, delete the rest."""
    result: dict[str, str] = {}
    for name in keep:
        if name in current:
            result[name] = str(current[name])
    for name, value in new_values.items():
        result[name] = await put_field(session, ctx, f"{prefix}:{name}", value)
    for name, ref in current.items():
        if name not in result:
            await delete_field(session, ctx, str(ref))
    return result


async def states(session: AsyncSession, workspace_id: uuid.UUID, refs: dict[str, Any]) -> dict[str, SecretFieldState]:
    out: dict[str, SecretFieldState] = {}
    ids = {name: parse_ref(str(ref)) for name, ref in refs.items() if ref}
    rows = (
        {
            s.id: s
            for s in (
                await session.scalars(
                    select(Secret).where(Secret.workspace_id == workspace_id, Secret.id.in_(ids.values()))
                )
            ).all()
        }
        if ids
        else {}
    )
    for name in refs:
        row = rows.get(ids.get(name)) if name in ids else None  # type: ignore[arg-type]
        out[name] = SecretFieldState(is_set=row is not None, hint=row.hint if row else None)
    return out


async def state(session: AsyncSession, workspace_id: uuid.UUID, ref: str | None) -> SecretFieldState:
    if not ref:
        return SecretFieldState(is_set=False)
    return (await states(session, workspace_id, {"v": ref}))["v"]
