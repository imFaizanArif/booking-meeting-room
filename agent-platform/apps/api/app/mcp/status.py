"""Connection status reporting: persists server status and publishes a workspace event."""

from __future__ import annotations

import sqlalchemy as sa

from app.core.enums import EventType, ServerStatus
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import session_scope
from app.events.publisher import publish_workspace_event
from app.mcp.types import ServerSpec
from app.models import MCPServer

log = get_logger(__name__)
_REPORTED = {ServerStatus.ready, ServerStatus.failed, ServerStatus.reconnecting, ServerStatus.disconnected}


async def report_status(spec: ServerSpec, status: ServerStatus, message: str | None) -> None:
    if status not in _REPORTED:
        return
    values: dict[str, object] = {"status": status, "status_message": message}
    if status == ServerStatus.ready:
        values["last_connected_at"] = utcnow()
    async with session_scope() as session:
        await session.execute(sa.update(MCPServer).where(MCPServer.id == spec.server_id).values(**values))
    await publish_workspace_event(
        spec.workspace_id,
        EventType.mcp_server_status_changed,
        server_id=spec.server_id,
        payload={"status": status.value, "message": message, "slug": spec.slug},
    )


async def tools_changed(spec: ServerSpec) -> None:
    """`notifications/tools/list_changed`: re-run discovery from the live connection."""
    from app.mcp.discovery import upsert_tools
    from app.mcp.manager import get_connection_manager

    conn = await get_connection_manager().get(spec)
    async with session_scope() as session:
        server = await session.get(MCPServer, spec.server_id)
        if server is not None:
            report = await upsert_tools(session, server, list(conn.tools.values()))
            log.info("mcp_tools_rediscovered", server=spec.slug, added=report.added, stale=report.stale)
