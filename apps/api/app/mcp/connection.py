"""One live MCP connection, owned by a dedicated asyncio task.

The transport and `ClientSession` are async context managers built on anyio cancel
scopes, which must be entered and exited in the same task. So a background task opens
them, publishes the session, and holds them open until `close()`; other tasks call tools
through the published session.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Awaitable, Callable
from typing import Any

import anyio
from mcp.client.session import ClientSession
from mcp.shared.exceptions import MCPError
from mcp.types import PaginatedRequestParams, Tool, ToolListChangedNotification

from app.core.enums import ServerStatus
from app.core.logging import get_logger
from app.mcp.transports import build_transport
from app.mcp.types import (
    DiscoveredTool,
    MCPConnectionFailed,
    MCPProtocolError,
    MCPToolTimeout,
    MCPTransportError,
    ServerSpec,
    ToolResult,
)

log = get_logger(__name__)
StatusCallback = Callable[[ServerSpec, ServerStatus, str | None], Awaitable[None]]
_TRANSPORT_ERRORS = (
    anyio.ClosedResourceError, anyio.BrokenResourceError, anyio.EndOfStream,
    ConnectionError, OSError, EOFError,
)
_MAX_PAGES = 50


def to_discovered(tool: Tool) -> DiscoveredTool:
    ann = tool.annotations.model_dump(by_alias=True, exclude_none=True) if tool.annotations else {}
    return DiscoveredTool(
        name=tool.name, title=tool.title, description=tool.description,
        input_schema=dict(tool.input_schema or {}),
        output_schema=dict(tool.output_schema) if tool.output_schema else None,
        annotations=ann,
    )


async def list_all_tools(session: ClientSession) -> list[DiscoveredTool]:
    tools: list[DiscoveredTool] = []
    cursor: str | None = None
    for _ in range(_MAX_PAGES):
        result = await session.list_tools(params=PaginatedRequestParams(cursor=cursor) if cursor else None)
        tools.extend(to_discovered(t) for t in result.tools)
        cursor = result.next_cursor
        if not cursor:
            break
    return tools


class MCPConnection:
    def __init__(self, spec: ServerSpec, on_status: StatusCallback | None = None,
                 on_tools_changed: Callable[[ServerSpec], Awaitable[None]] | None = None) -> None:
        self.spec = spec
        self.status = ServerStatus.disconnected
        self.error: str | None = None
        self.tools: dict[str, DiscoveredTool] = {}
        self.server_info: dict[str, Any] = {}
        self.last_used = time.monotonic()
        self.in_flight = 0
        self._session: ClientSession | None = None
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._closing = asyncio.Event()
        self._on_status = on_status
        self._on_tools_changed = on_tools_changed

    async def _set(self, status: ServerStatus, message: str | None = None) -> None:
        self.status = status
        if self._on_status is not None:
            try:
                await self._on_status(self.spec, status, message)
            except Exception as exc:  # status reporting must never break the connection
                log.warning("mcp_status_callback_failed", error=str(exc))

    async def _on_message(self, message: Any) -> None:
        if isinstance(message, ToolListChangedNotification) and self._on_tools_changed is not None:
            asyncio.create_task(self._refresh_tools())

    async def _refresh_tools(self) -> None:
        if self._session is None or self._on_tools_changed is None:
            return
        try:
            self.tools = {t.name: t for t in await list_all_tools(self._session)}
            await self._on_tools_changed(self.spec)
        except Exception as exc:
            log.warning("mcp_tool_refresh_failed", server=self.spec.slug, error=str(exc))

    async def _run(self) -> None:
        try:
            await self._set(ServerStatus.connecting)
            transport = build_transport(self.spec)
            async with contextlib.AsyncExitStack() as stack:
                async with asyncio.timeout(self.spec.connect_timeout_s):
                    read, write = await stack.enter_async_context(transport.open())
                    session = await stack.enter_async_context(
                        ClientSession(read, write, message_handler=self._on_message)
                    )
                    await self._set(ServerStatus.initializing)
                    init = await session.initialize()
                    info = getattr(init, "server_info", None)
                    self.server_info = info.model_dump(exclude_none=True) if info else {}
                    await self._set(ServerStatus.discovering)
                    self.tools = {t.name: t for t in await list_all_tools(session)}
                self._session = session
                self.error = None
                await self._set(ServerStatus.ready)
                self._ready.set()
                await self._closing.wait()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:  # noqa: BLE001 - ExceptionGroup from anyio task groups
            self.error = _describe(exc)
            log.warning("mcp_connection_failed", server=self.spec.slug, error=self.error)
            await self._set(ServerStatus.failed, self.error)
        finally:
            self._session = None
            self._ready.set()
            if self.status == ServerStatus.ready:
                await self._set(ServerStatus.disconnected)

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name=f"mcp:{self.spec.slug}")
        await self._ready.wait()
        if self._session is None:
            raise MCPConnectionFailed(
                f"Could not connect to MCP server {self.spec.slug}: {self.error or 'unknown error'}",
                details={"server": self.spec.slug},
            )

    @property
    def alive(self) -> bool:
        return self._session is not None and self._task is not None and not self._task.done()

    async def close(self, timeout: float = 10.0) -> None:
        self._closing.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            except BaseException:  # noqa: BLE001
                pass

    async def ping(self) -> None:
        if self._session is None:
            raise MCPTransportError("Connection is not open")
        async with asyncio.timeout(10):
            await self._session.send_ping()

    async def call_tool(
        self, name: str, arguments: dict[str, Any], *, timeout_s: float | None = None,
        meta: dict[str, Any] | None = None,
    ) -> ToolResult:
        if self._session is None:
            raise MCPTransportError(f"Connection to {self.spec.slug} is not open", details={"server": self.spec.slug})
        timeout = timeout_s or self.spec.call_timeout_s
        started = time.perf_counter()
        self.in_flight += 1
        self.last_used = time.monotonic()
        try:
            async with asyncio.timeout(timeout):
                result = await self._session.call_tool(name, arguments, meta=meta)
        except TimeoutError as exc:
            raise MCPToolTimeout(f"Tool {name} timed out after {timeout:.0f}s",
                                 details={"tool": name, "timeout_s": timeout}) from exc
        except MCPError as exc:
            raise MCPProtocolError(f"Server rejected {name}: {exc.message}",
                                   details={"tool": name, "code": exc.code}) from exc
        except _TRANSPORT_ERRORS as exc:
            raise MCPTransportError(f"Connection to {self.spec.slug} failed during {name}",
                                    details={"tool": name, "error": exc.__class__.__name__}) from exc
        finally:
            self.in_flight -= 1
        duration_ms = int((time.perf_counter() - started) * 1000)
        texts = [getattr(c, "text", None) for c in (result.content or [])]
        content = "\n".join(t for t in texts if t)
        is_error = bool(getattr(result, "is_error", False))
        return ToolResult(
            success=not is_error,
            tool_name=name,
            content=content,
            structured_content=getattr(result, "structured_content", None),
            error={"type": "tool_error", "message": content[:2000]} if is_error else None,
            metadata={"server": self.spec.slug},
            duration_ms=duration_ms,
        )


def _describe(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(_describe(e) for e in exc.exceptions)[:1000]
    if isinstance(exc, TimeoutError):
        return "timed out while connecting"
    return f"{exc.__class__.__name__}: {exc}"[:1000]
