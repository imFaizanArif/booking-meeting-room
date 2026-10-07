"""Authentication behind an `Authenticator` interface (password now, OIDC later)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit
from app.core.config import get_settings
from app.core.enums import AuditEventType, ErrorCode, Role
from app.core.errors import AppError, Unauthenticated
from app.core.security import hash_password, new_token, sha256_hex, verify_password
from app.core.time import utcnow
from app.models import User, UserSession, WorkspaceMember
from app.services.context import Actor, AuthContext


class InvalidCredentials(AppError):
    code = ErrorCode.invalid_credentials


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    context: AuthContext


class Authenticator(Protocol):
    async def authenticate(self, session: AsyncSession, email: str, secret: str) -> User: ...


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return hash_password(new_token())


class PasswordAuthenticator:
    async def authenticate(self, session: AsyncSession, email: str, secret: str) -> User:
        user = await session.scalar(select(User).where(User.email == email.lower().strip()))
        # Verify against a dummy hash when the user does not exist to keep timing uniform.
        hash_ = user.password_hash if user else _dummy_hash()
        if not verify_password(hash_, secret) or user is None or not user.is_active:
            raise InvalidCredentials("Email or password is incorrect")
        return user


async def login(
    session: AsyncSession,
    email: str,
    password: str,
    *,
    ip: str | None,
    user_agent: str | None,
    authenticator: Authenticator | None = None,
) -> IssuedSession:
    try:
        user = await (authenticator or PasswordAuthenticator()).authenticate(session, email, password)
    except InvalidCredentials:
        await audit(
            session,
            event_type=AuditEventType.auth_login_failed,
            actor=Actor("anonymous", None, email[:320]),
            workspace_id=None,
            payload={"email": email[:320], "ip": ip},
        )
        await session.commit()
        raise
    member = await session.scalar(
        select(WorkspaceMember).where(WorkspaceMember.user_id == user.id).order_by(WorkspaceMember.created_at)
    )
    if member is None:
        raise InvalidCredentials("This account has no workspace access")
    token, csrf = new_token(), new_token()
    session.add(
        UserSession(
            user_id=user.id,
            workspace_id=member.workspace_id,
            token_hash=sha256_hex(token),
            csrf_token=csrf,
            expires_at=utcnow() + timedelta(hours=get_settings().session_ttl_hours),
            ip=ip,
            user_agent=(user_agent or "")[:400],
        )
    )
    user.last_login_at = utcnow()
    ctx = AuthContext(user_id=user.id, workspace_id=member.workspace_id, role=member.role, email=user.email, ip=ip)
    await audit(session, event_type=AuditEventType.auth_login, actor=ctx, workspace_id=member.workspace_id)
    await session.commit()
    return IssuedSession(token=token, csrf_token=csrf, context=ctx)


async def resolve_session(session: AsyncSession, token: str | None) -> tuple[AuthContext, UserSession]:
    if not token:
        raise Unauthenticated("Sign in to continue")
    row = await session.scalar(select(UserSession).where(UserSession.token_hash == sha256_hex(token)))
    if row is None or row.revoked_at is not None or row.expires_at < utcnow():
        raise Unauthenticated("Your session has ended. Sign in again.")
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.user_id == row.user_id, WorkspaceMember.workspace_id == row.workspace_id
        )
    )
    user = await session.get(User, row.user_id)
    if member is None or user is None or not user.is_active:
        raise Unauthenticated("Your access has changed. Sign in again.")
    return AuthContext(user_id=user.id, workspace_id=row.workspace_id, role=Role(member.role), email=user.email), row


async def logout(session: AsyncSession, ctx: AuthContext, session_row_id: uuid.UUID) -> None:
    row = await session.get(UserSession, session_row_id)
    if row is not None:
        row.revoked_at = utcnow()
    await audit(session, event_type=AuditEventType.auth_logout, actor=ctx, workspace_id=ctx.workspace_id)
