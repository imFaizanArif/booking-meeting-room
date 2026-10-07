"""MCP layer value types, independent of the SDK."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import ErrorCode, IsolationMode, TransportType
from app.core.errors import AppError


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def schema_hash(input_schema: dict[str, Any], annotations: dict[str, Any] | None = None) -> str:
    return hashlib.sha256(canonical_json({"input": input_schema, "ann": annotations or {}}).encode()).hexdigest()


def namespaced(server_slug: str, tool_name: str) -> str:
    """LLM-facing name. Two servers may expose tools with the same name."""
    return f"{server_slug}__{tool_name}"[:64]


@dataclass(frozen=True)
class ServerSpec:
    """Everything needed to open a connection. Secrets are already decrypted (worker only)."""

    server_id: uuid.UUID
    workspace_id: uuid.UUID
    slug: str
    transport: TransportType
    command: str | None = None
    args: tuple[str, ...] = ()
    cwd: str | None = None
    url: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    headers: dict[str, str] = field(default_factory=dict)
    isolation: IsolationMode = IsolationMode.shared
    connect_timeout_s: float = 20.0
    call_timeout_s: float = 60.0
    config_hash: str = ""


def server_config_hash(
    transport: str,
    command: str | None,
    args: list[Any] | tuple[Any, ...],
    cwd: str | None,
    url: str | None,
    env_refs: dict[str, Any],
    header_refs: dict[str, Any],
    isolation: str,
) -> str:
    """Hash of connection-relevant config (refs, not values). A change retires pooled connections."""
    return hashlib.sha256(
        canonical_json(
            {
                "t": transport,
                "c": command,
                "a": list(args),
                "cwd": cwd,
                "u": url,
                "e": env_refs,
                "h": header_refs,
                "i": isolation,
            }
        ).encode()
    ).hexdigest()


class DiscoveredTool(BaseModel):
    name: str
    title: str | None = None
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] = Field(default_factory=dict)

    @property
    def schema_hash(self) -> str:
        return schema_hash(self.input_schema, self.annotations)


class ToolResult(BaseModel):
    """Normalised result of one tool call."""

    success: bool
    tool_name: str
    content: str = ""
    structured_content: Any = None
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: int = 0


class MCPConnectionFailed(AppError):
    code = ErrorCode.mcp_connection_failed
    retryable = True


class MCPTransportError(AppError):
    """The connection broke or timed out mid-call. Retryable for read-only tools only."""

    code = ErrorCode.mcp_connection_failed
    retryable = True


class MCPToolTimeout(AppError):
    code = ErrorCode.tool_timeout
    retryable = True


class MCPProtocolError(AppError):
    """The server answered with a JSON-RPC error (e.g. invalid params)."""

    code = ErrorCode.mcp_tool_error
