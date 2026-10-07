"""Per-process connection pool for MCP servers.

Key: (server_id, config_hash, isolation_key). `isolation_key` is "shared" unless the server
is configured `per_execution`, in which case it is the execution id and the connection is
closed when the execution releases it. Connections are never shared across processes.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import uuid
from collections.abc import Awaitable, Callable

from app.core.config import get_settings
from app.core.enums import IsolationMode, ServerStatus, TransportType
from app.core.logging import get_logger
from app.mcp.connection import MCPConnection, StatusCallback
from app.mcp.types import MCPConnectionFailed, ServerSpec

log = get_logger(__name__)
PoolKey = tuple[uuid.UUID, str, str]
SHARED = "shared"


class MCPConnectionManager:
    def __init__(
        self,
        *,
        max_stdio: int | None = None,
        on_status: StatusCallback | None = None,
        on_tools_changed: Callable[[ServerSpec], Awaitable[None]] | None = None,
        reconnect_attempts: int = 5,
    ) -> None:
        settings = get_settings()
        self._pool: dict[PoolKey, MCPConnection] = {}
        self._locks: dict[PoolKey, asyncio.Lock] = {}
        self._stdio = asyncio.Semaphore(max_stdio or settings.mcp_max_stdio_processes)
        self._stdio_held: set[PoolKey] = set()
        self._on_status = on_status
        self._on_tools_changed = on_tools_changed
        self._failures: dict[uuid.UUID, int] = {}
        self._reconnect_attempts = reconnect_attempts
        self._health_task: asyncio.Task[None] | None = None

    @staticmethod
    def key_for(spec: ServerSpec, execution_id: uuid.UUID | None) -> PoolKey:
        iso = str(execution_id) if spec.isolation == IsolationMode.per_execution and execution_id else SHARED
        return (spec.server_id, spec.config_hash, iso)

    async def get(self, spec: ServerSpec, execution_id: uuid.UUID | None = None) -> MCPConnection:
        key = self.key_for(spec, execution_id)
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            conn = self._pool.get(key)
            if conn is not None and conn.alive:
                return conn
            if conn is not None:
                await self._drop(key)
            await self._retire_stale(spec)
            return await self._open(key, spec)

    async def _open(self, key: PoolKey, spec: ServerSpec) -> MCPConnection:
        if spec.transport == TransportType.stdio:
            try:
                await asyncio.wait_for(self._stdio.acquire(), timeout=spec.connect_timeout_s)
            except TimeoutError as exc:
                raise MCPConnectionFailed(
                    "Too many MCP stdio processes in this worker", details={"server": spec.slug}
                ) from exc
            self._stdio_held.add(key)
        conn = MCPConnection(spec, on_status=self._on_status, on_tools_changed=self._on_tools_changed)
        try:
            await conn.start()
        except BaseException:
            await self._release_stdio(key)
            self._failures[spec.server_id] = self._failures.get(spec.server_id, 0) + 1
            raise
        self._failures.pop(spec.server_id, None)
        self._pool[key] = conn
        return conn

    async def _release_stdio(self, key: PoolKey) -> None:
        if key in self._stdio_held:
            self._stdio_held.discard(key)
            self._stdio.release()

    async def _drop(self, key: PoolKey) -> None:
        conn = self._pool.pop(key, None)
        if conn is not None:
            await conn.close()
        await self._release_stdio(key)

    async def _retire_stale(self, spec: ServerSpec) -> None:
        """A config change produces a new hash; idle connections with the old hash are closed."""
        for key in [k for k in self._pool if k[0] == spec.server_id and k[1] != spec.config_hash]:
            if self._pool[key].in_flight == 0:
                await self._drop(key)

    async def release_execution(self, execution_id: uuid.UUID) -> None:
        for key in [k for k in self._pool if k[2] == str(execution_id)]:
            await self._drop(key)

    async def disconnect_server(self, server_id: uuid.UUID) -> None:
        for key in [k for k in self._pool if k[0] == server_id]:
            await self._drop(key)

    def status(self, server_id: uuid.UUID) -> ServerStatus:
        conns = [c for k, c in self._pool.items() if k[0] == server_id]
        if any(c.alive for c in conns):
            return ServerStatus.ready
        return ServerStatus.disconnected

    async def health_loop(self, interval_s: float | None = None) -> None:
        interval = interval_s or get_settings().mcp_health_interval_s
        while True:
            await asyncio.sleep(interval)
            await self.check_health()

    async def check_health(self) -> None:
        for key, conn in list(self._pool.items()):
            if conn.in_flight:
                continue
            try:
                await conn.ping()
            except Exception as exc:  # noqa: BLE001 - any ping failure means reconnect
                log.warning("mcp_health_failed", server=conn.spec.slug, error=str(exc))
                await self._drop(key)
                await self._reconnect(key, conn.spec)

    async def _reconnect(self, key: PoolKey, spec: ServerSpec) -> None:
        if self._on_status is not None:
            await self._on_status(spec, ServerStatus.reconnecting, None)
        for attempt in range(self._reconnect_attempts):
            await asyncio.sleep(min(30.0, 0.5 * 2**attempt) + random.uniform(0, 0.5))
            try:
                await self._open(key, spec)
                return
            except Exception as exc:  # noqa: BLE001 - retried with backoff, then reported as failed
                log.info("mcp_reconnect_failed", server=spec.slug, attempt=attempt + 1, error=str(exc))
        if self._on_status is not None:
            await self._on_status(spec, ServerStatus.failed, "Reconnect attempts exhausted")

    def start_health_checks(self) -> None:
        if self._health_task is None:
            self._health_task = asyncio.create_task(self.health_loop(), name="mcp-health")

    async def shutdown(self) -> None:
        if self._health_task is not None:
            self._health_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._health_task
        await asyncio.gather(*(self._drop(k) for k in list(self._pool)), return_exceptions=True)


_manager: MCPConnectionManager | None = None


def get_connection_manager() -> MCPConnectionManager:
    global _manager
    if _manager is None:
        from app.mcp.status import report_status, tools_changed

        _manager = MCPConnectionManager(on_status=report_status, on_tools_changed=tools_changed)
    return _manager


def set_connection_manager(manager: MCPConnectionManager | None) -> None:
    global _manager
    _manager = manager
