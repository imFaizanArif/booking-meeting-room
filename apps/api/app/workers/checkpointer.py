"""LangGraph Postgres checkpointer backed by a psycopg connection pool."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.core.config import get_settings


@asynccontextmanager
async def open_checkpointer(max_size: int = 10) -> AsyncIterator[AsyncPostgresSaver]:
    pool = AsyncConnectionPool(
        get_settings().sync_database_url,
        min_size=1,
        max_size=max_size,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        open=False,
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await saver.setup()
        yield saver
    finally:
        await pool.close()
