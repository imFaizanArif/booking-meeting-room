"""Transport implementations behind one interface.

Adding a transport = one class here + one `TransportType` value. Verified against
mcp==2.3.0: `stdio_client`, `streamable_http_client(url, http_client=httpx2.AsyncClient)`
and `sse_client(url, headers=...)`.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Protocol

import httpx2
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from app.core.enums import TransportType
from app.core.ssrf import guard_url
from app.mcp.types import ServerSpec

Streams = tuple[Any, Any]

# A stdio server only inherits these from the worker environment; everything else must be
# configured explicitly on the server (values come from secrets).
_INHERITED_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT", "VIRTUAL_ENV")


class MCPTransport(Protocol):
    def open(self) -> AsyncIterator[Streams]: ...


class StdioTransport:
    def __init__(self, spec: ServerSpec) -> None:
        if not spec.command:
            raise ValueError("stdio transport requires a command")
        self.spec = spec

    def parameters(self) -> StdioServerParameters:
        env = {k: os.environ[k] for k in _INHERITED_ENV if k in os.environ}
        env.update(self.spec.env)
        return StdioServerParameters(
            command=self.spec.command or "", args=list(self.spec.args), env=env, cwd=self.spec.cwd
        )

    @asynccontextmanager
    async def open(self) -> AsyncIterator[Streams]:
        async with stdio_client(self.parameters(), errlog=sys.stderr) as streams:
            yield streams


class StreamableHttpTransport:
    def __init__(self, spec: ServerSpec) -> None:
        if not spec.url:
            raise ValueError("streamable_http transport requires a url")
        self.spec = spec

    @asynccontextmanager
    async def open(self) -> AsyncIterator[Streams]:
        url = self.spec.url or ""
        await guard_url(url)
        client = httpx2.AsyncClient(
            headers=self.spec.headers,
            timeout=httpx2.Timeout(self.spec.connect_timeout_s, read=max(self.spec.call_timeout_s, 30.0)),
        )
        async with client, streamable_http_client(url, http_client=client) as streams:
            yield streams


class SseLegacyTransport:
    """HTTP+SSE (2024-11-05 protocol). Compatibility only."""

    def __init__(self, spec: ServerSpec) -> None:
        if not spec.url:
            raise ValueError("sse_legacy transport requires a url")
        self.spec = spec

    @asynccontextmanager
    async def open(self) -> AsyncIterator[Streams]:
        url = self.spec.url or ""
        await guard_url(url)
        async with sse_client(
            url,
            headers=self.spec.headers,
            timeout=self.spec.connect_timeout_s,
            sse_read_timeout=max(self.spec.call_timeout_s, 60.0),
        ) as streams:
            yield streams


TRANSPORTS: dict[TransportType, type[StdioTransport] | type[StreamableHttpTransport] | type[SseLegacyTransport]] = {
    TransportType.stdio: StdioTransport,
    TransportType.streamable_http: StreamableHttpTransport,
    TransportType.sse_legacy: SseLegacyTransport,
}


def build_transport(spec: ServerSpec) -> StdioTransport | StreamableHttpTransport | SseLegacyTransport:
    return TRANSPORTS[spec.transport](spec)
