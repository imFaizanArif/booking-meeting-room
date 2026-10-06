"""Shared helpers for the demo servers: idempotency store and meta access."""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import Context


def state_dir() -> Path:
    path = Path(os.environ.get("MOCK_MCP_STATE_DIR", "/tmp/mock-mcp-state"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def idempotency_key(ctx: Context | None) -> str | None:
    if ctx is None:
        return None
    meta: Any = ctx.request_context.meta
    if meta is None:
        return None
    if isinstance(meta, dict):
        value = meta.get("idempotency_key")
    else:
        value = getattr(meta, "idempotency_key", None) or (getattr(meta, "model_extra", None) or {}).get(
            "idempotency_key"
        )
    return str(value) if value else None


def once(server: str, key: str | None, action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run `action` at most once per idempotency key, across processes (file lock).

    A repeated key returns the original result with `"replayed": true`.
    """
    path = state_dir() / f"{server}.json"
    with open(path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        raw = handle.read()
        data: dict[str, Any] = json.loads(raw) if raw.strip() else {"results": {}, "log": []}
        if key and key in data["results"]:
            return {**data["results"][key], "replayed": True}
        result = action()
        data["log"].append({"key": key, "result": result})
        if key:
            data["results"][key] = result
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(data))
        fcntl.flock(handle, fcntl.LOCK_UN)
    return {**result, "replayed": False}


def effects(server: str) -> list[dict[str, Any]]:
    """All side effects recorded by a server (used by tests to prove at-most-once)."""
    path = state_dir() / f"{server}.json"
    if not path.exists():
        return []
    raw = path.read_text(encoding="utf-8")
    return list(json.loads(raw)["log"]) if raw.strip() else []
