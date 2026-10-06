"""Job queue facade over arq. Producers (API, scheduler, worker) enqueue through here."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings

QUEUE_NAME = "agent-platform"


class Job(StrEnum):
    run_execution = "run_execution"
    resume_execution = "resume_execution"
    discover_server = "discover_server"
    test_server = "test_server"
    send_notification = "send_notification"
    test_provider = "test_provider"


class JobQueue(Protocol):
    async def enqueue(self, job: Job, *args: Any, job_id: str | None = None,
                      defer_until: datetime | None = None) -> str | None: ...

    async def call(self, job: Job, *args: Any, timeout_s: float = 30.0) -> Any: ...


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class ArqQueue:
    def __init__(self) -> None:
        self._pool: ArqRedis | None = None

    async def pool(self) -> ArqRedis:
        if self._pool is None:
            self._pool = await create_pool(redis_settings(), default_queue_name=QUEUE_NAME)
        return self._pool

    async def enqueue(self, job: Job, *args: Any, job_id: str | None = None,
                      defer_until: datetime | None = None) -> str | None:
        pool = await self.pool()
        handle = await pool.enqueue_job(job.value, *args, _job_id=job_id, _defer_until=defer_until,
                                        _queue_name=QUEUE_NAME)
        return handle.job_id if handle is not None else None

    async def call(self, job: Job, *args: Any, timeout_s: float = 30.0) -> Any:
        """Enqueue and wait for the result (used for interactive actions such as discovery)."""
        pool = await self.pool()
        handle = await pool.enqueue_job(job.value, *args, _job_id=f"{job.value}:{uuid.uuid4()}",
                                        _queue_name=QUEUE_NAME)
        if handle is None:
            raise RuntimeError("job was not enqueued")
        return await handle.result(timeout=timeout_s, poll_delay=0.2)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
        self._pool = None


_queue: JobQueue | None = None


def get_queue() -> JobQueue:
    global _queue
    if _queue is None:
        _queue = ArqQueue()
    return _queue


def set_queue(queue: JobQueue | None) -> None:
    global _queue
    _queue = queue


def resume_job_id(execution_id: uuid.UUID | str) -> str:
    """Unique per request: two decisions in a row must both be able to resume."""
    return f"resume:{execution_id}:{uuid.uuid4().hex[:8]}"
