"""Build connection specs from configuration rows. Decrypts env/header secrets (worker only)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit
from app.core.enums import AuditEventType, IsolationMode, TransportType
from app.mcp.types import ServerSpec, server_config_hash
from app.models import MCPServer
from app.secrets.manager import get_secret_manager
from app.services.context import WORKER_ACTOR, Actor


def compute_config_hash(server: MCPServer) -> str:
    return server_config_hash(
        server.transport.value,
        server.command,
        server.args or [],
        server.cwd,
        server.url,
        server.env_refs or {},
        server.header_refs or {},
        server.isolation.value,
    )


async def _resolve_refs(session: AsyncSession, server: MCPServer, refs: dict[str, Any], actor: Actor) -> dict[str, str]:
    manager = get_secret_manager()
    values: dict[str, str] = {}
    for name, ref in (refs or {}).items():
        values[name] = await manager.get(session, server.workspace_id, str(ref))
        await audit(
            session,
            event_type=AuditEventType.secret_accessed,
            actor=actor,
            workspace_id=server.workspace_id,
            entity_type="secret",
            entity_id=str(ref),
            payload={"purpose": f"mcp_server:{server.slug}", "field": name},
        )
    return values


async def build_spec(session: AsyncSession, server: MCPServer, actor: Actor = WORKER_ACTOR) -> ServerSpec:
    return ServerSpec(
        server_id=server.id,
        workspace_id=server.workspace_id,
        slug=server.slug,
        transport=TransportType(server.transport),
        command=server.command,
        args=tuple(str(a) for a in (server.args or [])),
        cwd=server.cwd,
        url=server.url,
        env=await _resolve_refs(session, server, server.env_refs, actor),
        headers=await _resolve_refs(session, server, server.header_refs, actor),
        isolation=IsolationMode(server.isolation),
        connect_timeout_s=server.connect_timeout_s,
        call_timeout_s=server.call_timeout_s,
        config_hash=server.config_hash or compute_config_hash(server),
    )
