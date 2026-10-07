from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query

from app.api.deps import DB, Auth
from app.schemas.common import Ok, Page
from app.schemas.config import (
    ChannelIn,
    ChannelOut,
    MemberIn,
    MemberOut,
    MemberPatch,
    SecretIn,
    SecretOut,
    WorkspaceOut,
    WorkspacePatch,
)
from app.schemas.runtime import AuditOut, DashboardOut
from app.services import dashboard as dashboard_service
from app.services import settings as service

router = APIRouter(tags=["settings"])


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(ctx: Auth, session: DB) -> DashboardOut:
    return await dashboard_service.dashboard(session, ctx)


@router.get("/audit", response_model=Page[AuditOut])
async def search_audit(
    ctx: Auth,
    session: DB,
    q: str | None = None,
    event_type: str | None = None,
    entity_type: str | None = None,
    execution_id: uuid.UUID | None = None,
    actor: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
) -> Page[AuditOut]:
    items, total = await dashboard_service.search_audit(
        session,
        ctx,
        q=q,
        event_type=event_type,
        entity_type=entity_type,
        execution_id=execution_id,
        actor=actor,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/workspace", response_model=WorkspaceOut)
async def get_workspace(ctx: Auth, session: DB) -> WorkspaceOut:
    return await service.get_workspace(session, ctx)


@router.patch("/workspace", response_model=WorkspaceOut)
async def update_workspace(data: WorkspacePatch, ctx: Auth, session: DB) -> WorkspaceOut:
    return await service.update_workspace(session, ctx, data)


@router.get("/members", response_model=list[MemberOut])
async def list_members(ctx: Auth, session: DB) -> list[MemberOut]:
    return await service.list_members(session, ctx)


@router.post("/members", response_model=MemberOut, status_code=201)
async def add_member(data: MemberIn, ctx: Auth, session: DB) -> MemberOut:
    return await service.add_member(session, ctx, data)


@router.patch("/members/{user_id}", response_model=MemberOut)
async def update_member(user_id: uuid.UUID, data: MemberPatch, ctx: Auth, session: DB) -> MemberOut:
    return await service.update_member(session, ctx, user_id, data)


@router.get("/notification-channels", response_model=list[ChannelOut])
async def list_channels(ctx: Auth, session: DB) -> list[ChannelOut]:
    return await service.list_channels(session, ctx)


@router.post("/notification-channels", response_model=ChannelOut, status_code=201)
async def create_channel(data: ChannelIn, ctx: Auth, session: DB) -> ChannelOut:
    return await service.save_channel(session, ctx, data)


@router.put("/notification-channels/{channel_id}", response_model=ChannelOut)
async def update_channel(channel_id: uuid.UUID, data: ChannelIn, ctx: Auth, session: DB) -> ChannelOut:
    return await service.save_channel(session, ctx, data, channel_id)


@router.delete("/notification-channels/{channel_id}", response_model=Ok)
async def delete_channel(channel_id: uuid.UUID, ctx: Auth, session: DB) -> Ok:
    await service.delete_channel(session, ctx, channel_id)
    return Ok()


@router.get("/secrets", response_model=list[SecretOut])
async def list_secrets(ctx: Auth, session: DB) -> list[SecretOut]:
    return await service.list_secrets(session, ctx)


@router.put("/secrets", response_model=SecretOut)
async def put_secret(data: SecretIn, ctx: Auth, session: DB) -> SecretOut:
    return await service.put_secret(session, ctx, data)


@router.delete("/secrets/{secret_id}", response_model=Ok)
async def delete_secret(secret_id: uuid.UUID, ctx: Auth, session: DB) -> Ok:
    await service.delete_secret(session, ctx, secret_id)
    return Ok()
