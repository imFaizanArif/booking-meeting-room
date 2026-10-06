"""Workspace settings: workspace, members/roles, notification channels, secrets."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit
from app.core.enums import AuditEventType, Role
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.security import hash_password
from app.core.ssrf import guard_url
from app.models import NotificationChannel, Secret, User, Workspace, WorkspaceMember
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
from app.secrets.manager import get_secret_manager, make_ref
from app.services import secret_fields
from app.services.context import AuthContext


async def get_workspace(session: AsyncSession, ctx: AuthContext) -> WorkspaceOut:
    ws = await session.get(Workspace, ctx.workspace_id)
    assert ws is not None
    return WorkspaceOut.model_validate(ws)


async def update_workspace(session: AsyncSession, ctx: AuthContext, data: WorkspacePatch) -> WorkspaceOut:
    ctx.require(Role.owner)
    ws = await session.get(Workspace, ctx.workspace_id)
    assert ws is not None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(ws, key, value)
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="workspace", entity_id=ws.id, payload=data.model_dump(exclude_unset=True))
    await session.flush()
    return WorkspaceOut.model_validate(ws)


async def list_members(session: AsyncSession, ctx: AuthContext) -> list[MemberOut]:
    rows = (await session.execute(
        select(WorkspaceMember, User).join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == ctx.workspace_id).order_by(User.email))).all()
    return [MemberOut(user_id=u.id, email=u.email, display_name=u.display_name, role=m.role,
                      last_login_at=u.last_login_at) for m, u in rows]


async def add_member(session: AsyncSession, ctx: AuthContext, data: MemberIn) -> MemberOut:
    ctx.require(Role.owner)
    email = data.email.lower().strip()
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, display_name=data.display_name, password_hash=hash_password(data.password))
        session.add(user)
        await session.flush()
    elif await session.scalar(select(WorkspaceMember.id).where(WorkspaceMember.user_id == user.id,
                                                               WorkspaceMember.workspace_id == ctx.workspace_id)):
        raise Conflict("This person is already a member")
    session.add(WorkspaceMember(workspace_id=ctx.workspace_id, user_id=user.id, role=data.role))
    await audit(session, event_type=AuditEventType.member_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="user", entity_id=user.id, payload={"email": email, "role": data.role.value,
                                                                "action": "added"})
    await session.flush()
    return MemberOut(user_id=user.id, email=user.email, display_name=user.display_name, role=data.role,
                     last_login_at=user.last_login_at)


async def update_member(session: AsyncSession, ctx: AuthContext, user_id: uuid.UUID, data: MemberPatch) -> MemberOut:
    ctx.require(Role.owner)
    member = await session.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == user_id,
                                                                WorkspaceMember.workspace_id == ctx.workspace_id))
    if member is None:
        raise NotFound("Member not found")
    if member.role == Role.owner and data.role != Role.owner:
        owners = (await session.scalars(select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == ctx.workspace_id, WorkspaceMember.role == Role.owner))).all()
        if len(owners) <= 1:
            raise ValidationFailed("A workspace needs at least one owner")
    before = member.role
    member.role = data.role
    user = await session.get(User, user_id)
    assert user is not None
    await audit(session, event_type=AuditEventType.member_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="user", entity_id=user_id, payload={"from": before.value, "to": data.role.value})
    await session.flush()
    return MemberOut(user_id=user.id, email=user.email, display_name=user.display_name, role=member.role,
                     last_login_at=user.last_login_at)


async def _channel_out(session: AsyncSession, c: NotificationChannel) -> ChannelOut:
    return ChannelOut(id=c.id, name=c.name, channel_type=c.channel_type,
                      url=await secret_fields.state(session, c.workspace_id, c.url_secret_ref),
                      signing_secret=await secret_fields.state(session, c.workspace_id, c.signing_secret_ref),
                      events=list(c.events or []), is_active=c.is_active, last_delivery_ok=c.last_delivery_ok,
                      last_delivery_at=c.last_delivery_at)


async def list_channels(session: AsyncSession, ctx: AuthContext) -> list[ChannelOut]:
    rows = (await session.scalars(select(NotificationChannel).where(
        NotificationChannel.workspace_id == ctx.workspace_id).order_by(NotificationChannel.name))).all()
    return [await _channel_out(session, r) for r in rows]


async def save_channel(session: AsyncSession, ctx: AuthContext, data: ChannelIn,
                       channel_id: uuid.UUID | None = None) -> ChannelOut:
    ctx.require(Role.owner)
    if data.url is not None:
        await guard_url(str(data.url))
    if channel_id is None:
        if data.url is None:
            raise ValidationFailed("A webhook URL is required", details={"fields": [
                {"field": "url", "message": "Paste the incoming webhook URL"}]})
        row = NotificationChannel(workspace_id=ctx.workspace_id, name=data.name, channel_type=data.channel_type,
                                  url_secret_ref="pending", events=data.events, is_active=data.is_active)
        session.add(row)
        await session.flush()
    else:
        found = await session.scalar(select(NotificationChannel).where(
            NotificationChannel.id == channel_id, NotificationChannel.workspace_id == ctx.workspace_id))
        if found is None:
            raise NotFound("Channel not found")
        row = found
        row.name, row.channel_type, row.events, row.is_active = data.name, data.channel_type, data.events, data.is_active
    if data.url is not None:
        row.url_secret_ref = await secret_fields.put_field(session, ctx, f"channel:{row.id}:url", str(data.url))
    if data.signing_secret:
        row.signing_secret_ref = await secret_fields.put_field(session, ctx, f"channel:{row.id}:signing",
                                                               data.signing_secret)
    await audit(session, event_type=AuditEventType.config_updated if channel_id else AuditEventType.config_created,
                actor=ctx, workspace_id=ctx.workspace_id, entity_type="notification_channel", entity_id=row.id,
                payload={"name": data.name, "type": data.channel_type.value, "events": data.events})
    await session.flush()
    return await _channel_out(session, row)


async def delete_channel(session: AsyncSession, ctx: AuthContext, channel_id: uuid.UUID) -> None:
    ctx.require(Role.owner)
    row = await session.scalar(select(NotificationChannel).where(
        NotificationChannel.id == channel_id, NotificationChannel.workspace_id == ctx.workspace_id))
    if row is None:
        raise NotFound("Channel not found")
    await secret_fields.delete_field(session, ctx, row.url_secret_ref)
    await secret_fields.delete_field(session, ctx, row.signing_secret_ref)
    await session.delete(row)
    await audit(session, event_type=AuditEventType.config_deleted, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="notification_channel", entity_id=channel_id, payload={"name": row.name})


def _secret_out(s: Secret) -> SecretOut:
    return SecretOut(id=s.id, ref=make_ref(s.id), name=s.name, description=s.description, hint=s.hint,
                     version=s.version, managed=s.managed, updated_at=s.updated_at)


async def list_secrets(session: AsyncSession, ctx: AuthContext) -> list[SecretOut]:
    ctx.require(Role.owner)
    rows = (await session.scalars(select(Secret).where(Secret.workspace_id == ctx.workspace_id)
                                  .order_by(Secret.managed, Secret.name))).all()
    return [_secret_out(s) for s in rows]


async def put_secret(session: AsyncSession, ctx: AuthContext, data: SecretIn) -> SecretOut:
    ctx.require(Role.owner)
    meta = await get_secret_manager().put(session, ctx.workspace_id, data.name, data.value,
                                          description=data.description)
    await audit(session, event_type=AuditEventType.secret_written, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="secret", entity_id=meta.id, payload={"name": data.name, "version": meta.version})
    row = await session.get(Secret, meta.id)
    assert row is not None
    await session.refresh(row)
    return _secret_out(row)


async def delete_secret(session: AsyncSession, ctx: AuthContext, secret_id: uuid.UUID) -> None:
    ctx.require(Role.owner)
    await secret_fields.delete_field(session, ctx, make_ref(secret_id))
