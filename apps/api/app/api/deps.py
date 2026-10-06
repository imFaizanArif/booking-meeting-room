"""FastAPI dependencies: DB session, authenticated context, CSRF and rate limits."""

from __future__ import annotations

import hmac
from collections.abc import AsyncIterator
from dataclasses import replace
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import ErrorCode
from app.core.errors import AppError
from app.core.logging import bind_context
from app.core.redis import get_redis
from app.db.session import session_factory
from app.ratelimit.limiter import Limit, TokenBucket
from app.services.auth import resolve_session
from app.services.context import AuthContext

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


async def db_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


DB = Annotated[AsyncSession, Depends(db_session)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def auth_context(request: Request, session: DB) -> AuthContext:
    settings = get_settings()
    ctx, row = await resolve_session(session, request.cookies.get(settings.session_cookie_name))
    if request.method not in _SAFE_METHODS:
        header = request.headers.get("x-csrf-token", "")
        if not header or not hmac.compare_digest(header, row.csrf_token):
            raise AppError("Missing or invalid CSRF token", code=ErrorCode.csrf_failed)
        await rate_limit(f"mut:{ctx.user_id}", Limit(settings.mutation_rate_per_minute, 60))
    request.state.session_row_id = row.id
    ctx = replace(ctx, request_id=getattr(request.state, "request_id", None), ip=client_ip(request))
    bind_context(user_id=ctx.user_id, workspace_id=ctx.workspace_id)
    return ctx


Auth = Annotated[AuthContext, Depends(auth_context)]


async def rate_limit(key: str, limit: Limit) -> None:
    try:
        bucket = TokenBucket(get_redis())
        await bucket.acquire(key, limit, wait=False)
    except AppError:
        raise
    except Exception:  # noqa: BLE001 - limiter outage must not take the API down
        return
