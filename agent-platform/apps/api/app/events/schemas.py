"""Typed event models. Exported through OpenAPI so the web app shares them."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import EventType


class ExecutionEventOut(BaseModel):
    id: uuid.UUID
    execution_id: uuid.UUID
    seq: int
    type: EventType
    node_id: str | None = None
    tool_call_id: uuid.UUID | None = None
    approval_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class WorkspaceEventOut(BaseModel):
    """Notification on the workspace stream (approvals, status changes, server health)."""

    type: EventType
    execution_id: uuid.UUID | None = None
    approval_id: uuid.UUID | None = None
    server_id: uuid.UUID | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    at: datetime


def execution_channel(execution_id: uuid.UUID | str) -> str:
    return f"events:execution:{execution_id}"


def workspace_channel(workspace_id: uuid.UUID | str) -> str:
    return f"events:workspace:{workspace_id}"
