"""Shared test configuration.

Environment is set before any `app` import because `get_settings()` is cached. Unit tests
use none of the fixtures below; integration and API tests opt in through their own
conftest (autouse `clean_runtime`).
"""

from __future__ import annotations

import io
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

JOBS_PORT = int(os.environ.get("TEST_MOCK_JOBS_PORT", "8821"))
STATE_DIR = tempfile.mkdtemp(prefix="ap-test-mock-mcp-")
TEST_DATABASE_URL = "postgresql+asyncpg://postgres@localhost:5432/agent_platform_test"

os.environ.update(
    {
        "ENVIRONMENT": "test",
        "DATABASE_URL": TEST_DATABASE_URL,
        "REDIS_URL": "redis://localhost:6379/5",
        "OUTBOUND_ALLOWLIST": '["127.0.0.1","localhost"]',
        "SEED_DEMO": "false",
        "MOCK_MCP_STATE_DIR": STATE_DIR,
        "MOCK_JOBS_URL": f"http://127.0.0.1:{JOBS_PORT}/mcp",
        "LOG_JSON": "false",
        "LOG_LEVEL": "INFO",
    }
)
assert "agent_platform_test" in os.environ["DATABASE_URL"]


class LogSink(io.TextIOBase):
    """Everything structlog/stdlib logging prints during the session, kept for secret scans."""

    def __init__(self) -> None:
        self.chunks: list[str] = []

    def write(self, s: str) -> int:
        self.chunks.append(s)
        return len(s)

    def flush(self) -> None:
        return None

    def text(self) -> str:
        return "".join(self.chunks)


LOG_SINK = LogSink()


def _configure_logging() -> None:
    from app.core.logging import configure_logging

    real = sys.stdout
    sys.stdout = LOG_SINK  # type: ignore[assignment]
    try:
        configure_logging("INFO", json=False)
    finally:
        sys.stdout = real


_configure_logging()

import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.enums import Role  # noqa: E402
from app.workers.queue import Job, set_queue  # noqa: E402

assert get_settings().database_url == TEST_DATABASE_URL


# ---- fake queue ---------------------------------------------------------------------------------


class FakeQueue:
    """Records enqueued jobs. `call` runs worker functions in-process (discover/test)."""

    def __init__(self) -> None:
        self.jobs: list[tuple[Job, tuple[Any, ...], str | None]] = []
        self.connections: Any = None

    async def enqueue(self, job: Job, *args: Any, job_id: str | None = None,
                      defer_until: Any = None) -> str | None:
        self.jobs.append((job, args, job_id))
        return job_id

    async def call(self, job: Job, *args: Any, timeout_s: float = 30.0) -> Any:
        from app.mcp.manager import MCPConnectionManager
        from app.workers import worker

        if self.connections is None:
            self.connections = MCPConnectionManager()
        fn = getattr(worker, job.value)
        return await fn({"connections": self.connections}, *args)

    def of(self, job: Job) -> list[tuple[Any, ...]]:
        return [args for j, args, _ in self.jobs if j == job]

    def clear(self) -> None:
        self.jobs.clear()


# ---- external processes ---------------------------------------------------------------------------


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


@pytest.fixture(scope="session")
def jobs_server() -> Iterator[str]:
    """Our own Streamable HTTP jobs server (not the dev instance on 8811)."""
    if _port_open(JOBS_PORT):
        raise RuntimeError(f"Port {JOBS_PORT} is busy; set TEST_MOCK_JOBS_PORT to a free port")
    env = {**os.environ, "MOCK_MCP_STATE_DIR": STATE_DIR}
    proc = subprocess.Popen(
        [sys.executable, "-m", "mock_mcp.jobs_server", "--http", "--port", str(JOBS_PORT)],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 20
    while not _port_open(JOBS_PORT):
        if proc.poll() is not None or time.monotonic() > deadline:
            proc.kill()
            raise RuntimeError("mock jobs server did not start")
        time.sleep(0.1)
    try:
        yield os.environ["MOCK_JOBS_URL"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def reset_effects() -> None:
    for path in Path(STATE_DIR).glob("*.json"):
        path.unlink()


# ---- database -----------------------------------------------------------------------------------


async def _reset_schema() -> None:
    engine = create_async_engine(TEST_DATABASE_URL, isolation_level="AUTOCOMMIT")
    async with engine.connect() as conn:
        await conn.execute(sa.text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(sa.text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest.fixture(scope="session")
def fake_queue() -> Iterator[FakeQueue]:
    queue = FakeQueue()
    set_queue(queue)
    yield queue
    set_queue(None)


@pytest.fixture(scope="session")
async def checkpointer(migrated: None) -> AsyncIterator[Any]:
    from app.workers.checkpointer import open_checkpointer

    async with open_checkpointer(max_size=5) as saver:
        yield saver


@pytest.fixture(scope="session")
async def migrated() -> AsyncIterator[None]:
    import asyncio

    from app.db.migrate import upgrade

    await _reset_schema()
    await asyncio.to_thread(upgrade)  # alembic's env.py runs its own event loop
    yield
    from app.core.redis import close_redis
    from app.db.session import dispose_engine

    await close_redis()
    await dispose_engine()


@pytest.fixture(scope="session")
async def seeded(migrated: None, checkpointer: Any, jobs_server: str, fake_queue: FakeQueue) -> AsyncIterator[
        dict[str, Any]]:
    from app.db.session import session_factory
    from app.seed.demo import seed_all

    async with session_factory()() as session:
        result = await seed_all(session, discover=True)
    assert not result["problems"], result["problems"]
    yield result
    if fake_queue.connections is not None:
        await fake_queue.connections.shutdown()


RUNTIME_TABLES = (
    "DELETE FROM executions",
    "DELETE FROM schedule_fires",
    "DELETE FROM user_sessions",
    "TRUNCATE checkpoints, checkpoint_writes, checkpoint_blobs",
)


@pytest.fixture
async def clean_runtime(seeded: dict[str, Any], fake_queue: FakeQueue) -> AsyncIterator[dict[str, Any]]:
    from app.core.redis import get_redis
    from app.db.session import session_scope

    async with session_scope() as session:
        for stmt in RUNTIME_TABLES:
            await session.execute(sa.text(stmt))
    await get_redis().flushdb()
    reset_effects()
    fake_queue.clear()
    yield seeded


# ---- runners ----------------------------------------------------------------------------------------


class RunnerFactory:
    """Builds ExecutionRunners. Each `new()` is a fresh "worker process" (own MCP pool)."""

    def __init__(self, checkpointer: Any, queue: FakeQueue) -> None:
        self.checkpointer = checkpointer
        self.queue = queue
        self.managers: list[Any] = []

    def new(self) -> Any:
        from app.mcp.manager import MCPConnectionManager
        from app.orchestration.runner import ExecutionRunner

        manager = MCPConnectionManager()
        self.managers.append(manager)
        return ExecutionRunner(checkpointer=self.checkpointer, connections=manager, queue=self.queue,
                               worker_id=f"test-worker-{uuid.uuid4().hex[:6]}")

    async def close(self) -> None:
        for manager in self.managers:
            await manager.shutdown()
        self.managers.clear()


@pytest.fixture
async def runners(checkpointer: Any, fake_queue: FakeQueue) -> AsyncIterator[RunnerFactory]:
    factory = RunnerFactory(checkpointer, fake_queue)
    yield factory
    await factory.close()


# ---- identities -------------------------------------------------------------------------------------


async def auth_context(email: str) -> Any:
    from sqlalchemy import select

    from app.db.session import session_scope
    from app.models import User, WorkspaceMember
    from app.services.context import AuthContext

    async with session_scope() as session:
        user = await session.scalar(select(User).where(User.email == email))
        assert user is not None, email
        member = await session.scalar(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
        assert member is not None
        return AuthContext(user_id=user.id, workspace_id=member.workspace_id, role=Role(member.role),
                           email=user.email)


@pytest.fixture
async def operator_ctx(clean_runtime: dict[str, Any]) -> Any:
    return await auth_context("operator@example.com")


@pytest.fixture
async def owner_ctx(clean_runtime: dict[str, Any]) -> Any:
    return await auth_context("admin@example.com")


def pytest_configure(config: pytest.Config) -> None:
    # alembic.ini predates `path_separator`; not ours to change from the test suite.
    config.addinivalue_line("filterwarnings", "ignore:No path_separator found:DeprecationWarning")
