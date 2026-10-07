"""Async engine and session factory. One engine per process."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_factory: async_sessionmaker[AsyncSession] | None = None


def engine_kwargs() -> dict[str, Any]:
    """asyncpg options for hosted Postgres. PgBouncer in transaction mode (Supabase :6543) cannot
    keep prepared statements across transactions, so the statement cache is disabled and every
    prepared statement gets a unique name."""
    settings = get_settings()
    connect_args: dict[str, Any] = {}
    if settings.db_ssl:
        connect_args["ssl"] = "require"
    if settings.db_pooler == "transaction":
        connect_args["statement_cache_size"] = 0
        connect_args["prepared_statement_name_func"] = lambda: f"__ap_{uuid.uuid4().hex}__"
    return {"connect_args": connect_args, "pool_pre_ping": True}


def get_engine() -> AsyncEngine:
    global _engine, _factory
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url, pool_size=settings.database_pool_size, max_overflow=20, **engine_kwargs()
        )
        _factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _factory is not None
    return _factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Unit of work: commit on success, roll back on error."""
    async with session_factory()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _factory = None
