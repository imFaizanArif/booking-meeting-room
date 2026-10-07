"""Discovery over stdio and Streamable HTTP: safe defaults, stale detection, operator flags kept."""

from __future__ import annotations

import sys
from collections.abc import AsyncIterator
from typing import Any

import pytest
from sqlalchemy import delete, select

from app.core.enums import IsolationMode, RiskLevel, TransportType
from app.core.time import utcnow
from app.db.session import session_scope
from app.mcp.discovery import upsert_tools
from app.mcp.manager import MCPConnectionManager
from app.mcp.specs import build_spec, compute_config_hash
from app.models import MCPServer, MCPTool
from app.services.context import AuthContext
from app.workers import worker


async def _server(ctx: AuthContext, slug: str, transport: TransportType, **values: Any) -> MCPServer:
    async with session_scope() as session:
        row = MCPServer(
            workspace_id=ctx.workspace_id,
            slug=slug,
            name=slug,
            transport=transport,
            isolation=IsolationMode.shared,
            is_active=True,
            env_refs={},
            header_refs={},
            **values,
        )
        session.add(row)
        await session.flush()
        row.config_hash = compute_config_hash(row)
    return row


async def _tools(server_id: Any) -> dict[str, MCPTool]:
    async with session_scope() as session:
        return {t.name: t for t in (await session.scalars(select(MCPTool).where(MCPTool.server_id == server_id))).all()}


@pytest.fixture
async def manager() -> AsyncIterator[MCPConnectionManager]:
    m = MCPConnectionManager()
    yield m
    await m.shutdown()


@pytest.fixture
async def servers(operator_ctx: AuthContext, jobs_server: str) -> AsyncIterator[dict[str, MCPServer]]:
    made = {
        "stdio": await _server(
            operator_ctx,
            "disc_calendar",
            TransportType.stdio,
            command=sys.executable,
            args=["-m", "mock_mcp.calendar_server"],
            command_confirmed_at=utcnow(),
        ),
        "http": await _server(operator_ctx, "disc_jobs", TransportType.streamable_http, url=jobs_server),
    }
    yield made
    async with session_scope() as session:
        await session.execute(delete(MCPServer).where(MCPServer.id.in_([s.id for s in made.values()])))


async def test_new_tools_default_disabled_and_gated_unless_read_only(
    servers: dict[str, MCPServer],
    manager: MCPConnectionManager,
) -> None:
    for kind in ("stdio", "http"):
        result = await worker.discover_server({"connections": manager}, str(servers[kind].id))
        assert result["ok"], result
    calendar = await _tools(servers["stdio"].id)
    jobs = await _tools(servers["http"].id)
    assert set(calendar) == {"check_availability", "create_event"}
    assert set(jobs) == {"search_jobs", "get_job", "submit_proposal"}
    for tool in [*calendar.values(), *jobs.values()]:
        assert tool.is_enabled is False and tool.is_stale is False
        assert len(tool.schema_hash) == 64

    read_only = calendar["check_availability"]
    assert (read_only.is_read_only, read_only.requires_approval, read_only.risk_level) == (True, False, RiskLevel.low)
    not_destructive = calendar["create_event"]  # destructiveHint=false, but still a write
    assert (
        not_destructive.is_read_only,
        not_destructive.is_destructive,
        not_destructive.requires_approval,
        not_destructive.risk_level,
    ) == (False, False, True, RiskLevel.medium)
    destructive = jobs["submit_proposal"]
    assert (destructive.is_destructive, destructive.requires_approval, destructive.risk_level) == (
        True,
        True,
        RiskLevel.high,
    )
    assert jobs["search_jobs"].requires_approval is False


async def test_removed_and_renamed_tools_become_stale_and_flags_survive(
    servers: dict[str, MCPServer],
    manager: MCPConnectionManager,
) -> None:
    server = servers["stdio"]
    async with session_scope() as session:
        row = await session.get(MCPServer, server.id)
        assert row is not None
        conn = await manager.get(await build_spec(session, row))
    live = list(conn.tools.values())
    async with session_scope() as session:
        row = await session.get(MCPServer, server.id)
        report = await upsert_tools(session, row, live)  # type: ignore[arg-type]
    assert sorted(report.added) == ["check_availability", "create_event"]

    # An operator relaxes a flag; rediscovery must not overwrite it.
    async with session_scope() as session:
        tool = await session.scalar(
            select(MCPTool).where(MCPTool.server_id == server.id, MCPTool.name == "create_event")
        )
        assert tool is not None
        tool.requires_approval = False
        tool.is_enabled = True

    # The server renames check_availability and drops create_event.
    renamed = [t.model_copy(update={"name": "check_availability_v2"}) for t in live if t.name == "check_availability"]
    async with session_scope() as session:
        row = await session.get(MCPServer, server.id)
        report = await upsert_tools(session, row, renamed)  # type: ignore[arg-type]
    assert report.added == ["check_availability_v2"]
    assert sorted(report.stale) == ["check_availability", "create_event"]
    tools = await _tools(server.id)
    assert tools["check_availability"].is_stale and tools["create_event"].is_stale
    assert not tools["check_availability_v2"].is_stale and not tools["check_availability_v2"].is_enabled

    # The tool comes back with a changed schema: un-staled, hash updated, operator flags intact.
    changed = [
        t.model_copy(update={"input_schema": {**t.input_schema, "description": "v2"}})
        for t in live
        if t.name == "create_event"
    ]
    before_hash = tools["create_event"].schema_hash
    async with session_scope() as session:
        row = await session.get(MCPServer, server.id)
        report = await upsert_tools(session, row, changed)  # type: ignore[arg-type]
    assert report.schema_changed == ["create_event"]
    tools = await _tools(server.id)
    assert not tools["create_event"].is_stale
    assert tools["create_event"].schema_hash != before_hash
    assert tools["create_event"].requires_approval is False and tools["create_event"].is_enabled is True
