from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import DB, Auth
from app.schemas.common import Ok
from app.schemas.config import (
    DiscoveryOut,
    MCPServerIn,
    MCPServerOut,
    MCPToolBulk,
    MCPToolOut,
    MCPToolPatch,
    TestResult,
)
from app.services import mcp_config as service

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/servers", response_model=list[MCPServerOut])
async def list_servers(ctx: Auth, session: DB) -> list[MCPServerOut]:
    return await service.list_servers(session, ctx)


@router.post("/servers", response_model=MCPServerOut, status_code=201)
async def create_server(data: MCPServerIn, ctx: Auth, session: DB) -> MCPServerOut:
    return await service.create_server(session, ctx, data)


@router.get("/servers/{server_id}", response_model=MCPServerOut)
async def get_server(server_id: uuid.UUID, ctx: Auth, session: DB) -> MCPServerOut:
    return await service.get_server(session, ctx, server_id)


@router.put("/servers/{server_id}", response_model=MCPServerOut)
async def update_server(server_id: uuid.UUID, data: MCPServerIn, ctx: Auth, session: DB) -> MCPServerOut:
    return await service.update_server(session, ctx, server_id, data)


@router.delete("/servers/{server_id}", response_model=Ok)
async def delete_server(server_id: uuid.UUID, ctx: Auth, session: DB) -> Ok:
    await service.delete_server(session, ctx, server_id)
    return Ok()


@router.post("/servers/{server_id}/test", response_model=TestResult)
async def test_server(server_id: uuid.UUID, ctx: Auth, session: DB) -> TestResult:
    return await service.test_server(session, ctx, server_id)


@router.post("/servers/{server_id}/discover", response_model=DiscoveryOut)
async def discover_tools(server_id: uuid.UUID, ctx: Auth, session: DB) -> DiscoveryOut:
    return await service.discover(session, ctx, server_id)


@router.post("/servers/{server_id}/reconnect", response_model=TestResult)
async def reconnect_server(server_id: uuid.UUID, ctx: Auth, session: DB) -> TestResult:
    return await service.test_server(session, ctx, server_id)


@router.get("/tools", response_model=list[MCPToolOut])
async def list_tools(ctx: Auth, session: DB, server_id: uuid.UUID | None = None,
                     include_stale: bool = True) -> list[MCPToolOut]:
    return await service.list_tools(session, ctx, server_id, include_stale)


@router.patch("/tools/{tool_id}", response_model=MCPToolOut)
async def update_tool(tool_id: uuid.UUID, data: MCPToolPatch, ctx: Auth, session: DB) -> MCPToolOut:
    return await service.update_tool(session, ctx, tool_id, data)


@router.post("/tools/bulk", response_model=list[MCPToolOut])
async def bulk_update_tools(data: MCPToolBulk, ctx: Auth, session: DB) -> list[MCPToolOut]:
    return await service.bulk_update_tools(session, ctx, data)
