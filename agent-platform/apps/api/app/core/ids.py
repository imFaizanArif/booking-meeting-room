"""Identifier helpers: UUIDv7 primary keys, slugs and idempotency keys."""

from __future__ import annotations

import hashlib
import re
import uuid

import uuid_utils


def new_id() -> uuid.UUID:
    """Time-ordered UUIDv7 so primary keys index well."""
    return uuid.UUID(str(uuid_utils.uuid7()))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "item"


def idempotency_key(execution_id: uuid.UUID | str, node_id: str, call_seq: int) -> str:
    """Deterministic key for one tool call position inside an execution.

    Replaying a node from its checkpoint yields the same keys, so recorded calls are reused.
    """
    return f"{execution_id}:{node_id}:{call_seq}"


def external_idempotency_key(key: str) -> str:
    """Opaque form sent to MCP servers (no internal ids leak)."""
    return hashlib.sha256(key.encode()).hexdigest()[:32]
