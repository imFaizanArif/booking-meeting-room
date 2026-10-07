"""MCP servers and tools. Connecting/discovering runs in the worker; the API only asks."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit, diff
from app.core.enums import AuditEventType, Role, TransportType
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.ids import slugify
from app.core.redaction import redactor
from app.core.ssrf import guard_url
from app.core.time import utcnow
from app.mcp.specs import compute_config_hash
from app.mcp.types import namespaced
from app.models import MCPServer, MCPTool
from app.schemas.config import (
    DiscoveryOut,
    MCPServerIn,
    MCPServerOut,
    MCPToolBulk,
    MCPToolOut,
    MCPToolPatch,
    TestResult,
)
from app.services import secret_fields
from app.services.context import AuthContext
from app.workers.queue import Job, get_queue


async def server_out(session: AsyncSession, s: MCPServer) -> MCPServerOut:
    counts = (await session.execute(
        select(func.count(), func.count().filter(MCPTool.is_enabled.is_(True)))
        .where(MCPTool.server_id == s.id, MCPTool.is_stale.is_(False))
    )).one()
    return MCPServerOut(
        id=s.id, name=s.name, slug=s.slug, description=s.description, transport=s.transport, command=s.command,
        args=list(s.args or []), cwd=s.cwd, url=s.url,
        env=await secret_fields.states(session, s.workspace_id, s.env_refs or {}),
        headers=await secret_fields.states(session, s.workspace_id, s.header_refs or {}),
        isolation=s.isolation, status=s.status, status_message=s.status_message, is_active=s.is_active,
        connect_timeout_s=s.connect_timeout_s, call_timeout_s=s.call_timeout_s,
        requests_per_minute=s.requests_per_minute, last_connected_at=s.last_connected_at,
        last_discovered_at=s.last_discovered_at, command_confirmed_at=s.command_confirmed_at,
        tool_count=counts[0], enabled_tool_count=counts[1], created_at=s.created_at, updated_at=s.updated_at,
    )


async def _get(session: AsyncSession, ctx: AuthContext, server_id: uuid.UUID) -> MCPServer:
    row = await session.scalar(select(MCPServer).where(MCPServer.id == server_id,
                                                       MCPServer.workspace_id == ctx.workspace_id))
    if row is None:
        raise NotFound("MCP server not found")
    return row


def _snapshot(s: MCPServer) -> dict[str, Any]:
    return {"name": s.name, "transport": s.transport.value, "command": s.command, "args": s.args, "url": s.url,
            "env": sorted((s.env_refs or {}).keys()), "headers": sorted((s.header_refs or {}).keys()),
            "isolation": s.isolation.value, "is_active": s.is_active}


async def _validate(ctx: AuthContext, data: MCPServerIn) -> None:
    if data.transport == TransportType.stdio:
        ctx.require(Role.owner)  # stdio servers run local commands
        if not data.command:
            raise ValidationFailed("stdio servers need a command",
                                   details={"fields": [{"field": "command", "message": "Required for stdio"}]})
        if data.is_active and not data.confirm_command:
            raise ValidationFailed(
                "Confirm the exact command before activating a stdio server",
                details={"fields": [{"field": "confirm_command", "message": "Review the command and confirm"}]})
    else:
        if not data.url:
            raise ValidationFailed("Remote servers need a URL",
                                   details={"fields": [{"field": "url", "message": "Required for HTTP transports"}]})
        await guard_url(data.url)


async def list_servers(session: AsyncSession, ctx: AuthContext) -> list[MCPServerOut]:
    rows = (await session.scalars(select(MCPServer).where(MCPServer.workspace_id == ctx.workspace_id)
                                  .order_by(MCPServer.name))).all()
    return [await server_out(session, r) for r in rows]


async def get_server(session: AsyncSession, ctx: AuthContext, server_id: uuid.UUID) -> MCPServerOut:
    return await server_out(session, await _get(session, ctx, server_id))


async def create_server(session: AsyncSession, ctx: AuthContext, data: MCPServerIn) -> MCPServerOut:
    ctx.require(Role.owner if data.transport == TransportType.stdio else Role.operator)
    await _validate(ctx, data)
    slug = data.slug or slugify(data.name)[:40]
    if await session.scalar(select(MCPServer.id).where(MCPServer.workspace_id == ctx.workspace_id,
                                                       MCPServer.slug == slug)):
        raise Conflict("A server with this slug already exists", details={"fields": [
            {"field": "slug", "message": "Choose a different slug"}]})
    server = MCPServer(
        workspace_id=ctx.workspace_id, name=data.name, slug=slug, description=data.description,
        transport=data.transport, command=data.command, args=data.args, cwd=data.cwd, url=data.url,
        isolation=data.isolation, is_active=data.is_active, connect_timeout_s=data.connect_timeout_s,
        call_timeout_s=data.call_timeout_s, requests_per_minute=data.requests_per_minute,
        command_confirmed_at=utcnow() if data.confirm_command and data.transport == TransportType.stdio else None,
    )
    session.add(server)
    await session.flush()
    server.env_refs = await secret_fields.update_map(session, ctx, prefix=f"mcp:{server.id}:env", current={},
                                                     new_values=data.env, keep=[])
    server.header_refs = await secret_fields.update_map(session, ctx, prefix=f"mcp:{server.id}:header", current={},
                                                        new_values=data.headers, keep=[])
    server.config_hash = compute_config_hash(server)
    await audit(session, event_type=AuditEventType.config_created, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="mcp_server", entity_id=server.id, payload=_snapshot(server))
    await session.flush()
    return await server_out(session, server)


async def update_server(session: AsyncSession, ctx: AuthContext, server_id: uuid.UUID,
                        data: MCPServerIn) -> MCPServerOut:
    server = await _get(session, ctx, server_id)
    ctx.require(Role.owner if TransportType.stdio in (server.transport, data.transport) else Role.operator)
    await _validate(ctx, data)
    before = _snapshot(server)
    command_changed = (server.command, list(server.args or [])) != (data.command, data.args)
    for key in ("name", "description", "transport", "command", "args", "cwd", "url", "isolation", "is_active",
                "connect_timeout_s", "call_timeout_s", "requests_per_minute"):
        setattr(server, key, getattr(data, key))
    if data.slug and data.slug != server.slug:
        server.slug = data.slug
    if server.transport == TransportType.stdio:
        if data.confirm_command:
            server.command_confirmed_at = utcnow()
        elif command_changed:
            server.command_confirmed_at = None
            if server.is_active:
                raise ValidationFailed("The command changed. Confirm it before keeping the server active.",
                                       details={"fields": [{"field": "confirm_command", "message": "Confirm"}]})
    server.env_refs = await secret_fields.update_map(session, ctx, prefix=f"mcp:{server.id}:env",
                                                     current=dict(server.env_refs or {}), new_values=data.env,
                                                     keep=data.env_keep)
    server.header_refs = await secret_fields.update_map(session, ctx, prefix=f"mcp:{server.id}:header",
                                                        current=dict(server.header_refs or {}),
                                                        new_values=data.headers, keep=data.headers_keep)
    server.config_hash = compute_config_hash(server)
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="mcp_server", entity_id=server.id, payload={"changes": diff(before, _snapshot(server))})
    await session.flush()
    return await server_out(session, server)


async def delete_server(session: AsyncSession, ctx: AuthContext, server_id: uuid.UUID) -> None:
    server = await _get(session, ctx, server_id)
    ctx.require(Role.owner)
    for ref in list((server.env_refs or {}).values()) + list((server.header_refs or {}).values()):
        await secret_fields.delete_field(session, ctx, str(ref))
    await session.delete(server)
    await audit(session, event_type=AuditEventType.config_deleted, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="mcp_server", entity_id=server_id, payload={"name": server.name})


async def _worker_call(job: Job, server_id: uuid.UUID, timeout_s: float = 45) -> dict[str, Any]:
    try:
        result: dict[str, Any] = await get_queue().call(job, str(server_id), timeout_s=timeout_s)
    except TimeoutError:
        return {"ok": False, "message": f"No worker answered within {timeout_s:.0f}s. Is the worker running?"}
    result["message"] = redactor.redact_text(str(result.get("message", "")))[:1000]
    return result


async def test_server(session: AsyncSession, ctx: AuthContext, server_id: uuid.UUID) -> TestResult:
    ctx.require(Role.operator)
    server = await _get(session, ctx, server_id)
    await session.commit()
    result = await _worker_call(Job.test_server, server.id)
    return TestResult(ok=bool(result.get("ok")), message=result["message"],
                      details={"server_info": result.get("server_info") or {}})


async def discover(session: AsyncSession, ctx: AuthContext, server_id: uuid.UUID) -> DiscoveryOut:
    ctx.require(Role.operator)
    server = await _get(session, ctx, server_id)
    await session.commit()
    result = await _worker_call(Job.discover_server, server.id, timeout_s=60)
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="mcp_server", entity_id=server_id,
                payload={"action": "discover", "ok": result.get("ok"), "added": result.get("added"),
                         "stale": result.get("stale")})
    return DiscoveryOut(ok=bool(result.get("ok")), message=result["message"],
                        added=result.get("added") or [], updated=result.get("updated") or [],
                        stale=result.get("stale") or [], schema_changed=result.get("schema_changed") or [])


# ---- tools --------------------------------------------------------------------------------------


async def list_tools(session: AsyncSession, ctx: AuthContext, server_id: uuid.UUID | None = None,
                     include_stale: bool = True) -> list[MCPToolOut]:
    query = select(MCPTool, MCPServer.slug, MCPServer.name).join(MCPServer, MCPServer.id == MCPTool.server_id) \
        .where(MCPTool.workspace_id == ctx.workspace_id)
    if server_id:
        query = query.where(MCPTool.server_id == server_id)
    if not include_stale:
        query = query.where(MCPTool.is_stale.is_(False))
    rows = (await session.execute(query.order_by(MCPServer.name, MCPTool.name))).all()
    out = []
    for tool, slug, server_name in rows:
        item = MCPToolOut.model_validate(tool)
        item.server_slug, item.server_name, item.namespaced_name = slug, server_name, namespaced(slug, tool.name)
        out.append(item)
    return out


async def update_tool(session: AsyncSession, ctx: AuthContext, tool_id: uuid.UUID, data: MCPToolPatch) -> MCPToolOut:
    ctx.require(Role.operator)
    tool = await session.scalar(select(MCPTool).where(MCPTool.id == tool_id, MCPTool.workspace_id == ctx.workspace_id))
    if tool is None:
        raise NotFound("Tool not found")
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    if changes.get("is_enabled") and tool.is_stale:
        raise ValidationFailed("This tool no longer exists on the server. Re-run discovery.")
    before = {k: getattr(tool, k) for k in changes}
    for key, value in changes.items():
        setattr(tool, key, value)
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="mcp_tool", entity_id=tool.id,
                payload={"tool": tool.name, "changes": diff({k: str(v) for k, v in before.items()},
                                                            {k: str(v) for k, v in changes.items()})})
    await session.flush()
    return next(t for t in await list_tools(session, ctx, tool.server_id) if t.id == tool.id)


async def bulk_update_tools(session: AsyncSession, ctx: AuthContext, data: MCPToolBulk) -> list[MCPToolOut]:
    ctx.require(Role.operator)
    changes = data.patch.model_dump(exclude_unset=True, exclude_none=True)
    if not changes:
        raise ValidationFailed("Nothing to change")
    query = sa.update(MCPTool).where(MCPTool.workspace_id == ctx.workspace_id, MCPTool.id.in_(data.tool_ids))
    if changes.get("is_enabled"):
        query = query.where(MCPTool.is_stale.is_(False))
    await session.execute(query.values(**changes))
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="mcp_tool", entity_id=None,
                payload={"bulk": [str(i) for i in data.tool_ids], "changes": {k: str(v) for k, v in changes.items()}})
    await session.flush()
    ids = set(data.tool_ids)
    return [t for t in await list_tools(session, ctx) if t.id in ids]
