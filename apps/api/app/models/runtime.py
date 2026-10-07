"""Execution read model, side-effect records, usage, timers and events."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    ApprovalKind,
    ApprovalStatus,
    EventType,
    ExecutionStatus,
    NodeStatus,
    NodeType,
    ToolCallStatus,
    TriggerKind,
)
from app.db.base import Base, IdMixin, TimestampMixin, WorkspaceScoped, enum_col


class Execution(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "executions"
    __table_args__ = (
        sa.Index("ix_executions_ws_status_created", "workspace_id", "status", "created_at"),
        sa.Index("ix_executions_lease", "status", "lease_expires_at"),
    )

    pipeline_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("pipelines.id", ondelete="CASCADE"), index=True)
    pipeline_version_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("pipeline_versions.id", ondelete="RESTRICT"), index=True
    )
    trigger: Mapped[TriggerKind] = mapped_column(enum_col(TriggerKind, name="trigger_kind"))
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("schedules.id", ondelete="SET NULL"))
    restarted_from_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("executions.id", ondelete="SET NULL"))
    status: Mapped[ExecutionStatus] = mapped_column(enum_col(ExecutionStatus, name="execution_status"))
    input: Mapped[dict[str, Any]] = mapped_column(default=dict)
    output: Mapped[dict[str, Any] | None]
    config_snapshot: Mapped[dict[str, Any]]
    thread_id: Mapped[str] = mapped_column(sa.String(80), unique=True)
    error: Mapped[dict[str, Any] | None]
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    pause_requested: Mapped[bool] = mapped_column(default=False)
    retries_used: Mapped[int] = mapped_column(default=0)
    lease_owner: Mapped[str | None] = mapped_column(sa.String(120))
    lease_expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_event_seq: Mapped[int] = mapped_column(sa.BigInteger, default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(sa.Numeric(14, 6), default=Decimal(0))


class ExecutionNode(IdMixin, TimestampMixin, Base):
    __tablename__ = "execution_nodes"
    __table_args__ = (sa.UniqueConstraint("execution_id", "node_id"),)

    execution_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("executions.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(sa.String(100))
    node_type: Mapped[NodeType] = mapped_column(enum_col(NodeType, name="node_type"))
    name: Mapped[str] = mapped_column(sa.String(200))
    status: Mapped[NodeStatus] = mapped_column(enum_col(NodeStatus, name="node_status"))
    attempts: Mapped[int] = mapped_column(default=0)
    input_summary: Mapped[dict[str, Any] | None]
    output_summary: Mapped[dict[str, Any] | None]
    error: Mapped[dict[str, Any] | None]
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class ExecutionEvent(IdMixin, Base):
    """Persisted copy of every published event. (execution_id, seq) is gap-free."""

    __tablename__ = "execution_events"
    __table_args__ = (sa.UniqueConstraint("execution_id", "seq"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("workspaces.id", ondelete="CASCADE"), index=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("executions.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(sa.BigInteger)
    type: Mapped[EventType] = mapped_column(enum_col(EventType, name="event_type"))
    node_id: Mapped[str | None] = mapped_column(sa.String(100))
    tool_call_id: Mapped[uuid.UUID | None]
    approval_id: Mapped[uuid.UUID | None]
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


class ToolCall(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        sa.UniqueConstraint("idempotency_key"),
        sa.Index("ix_tool_calls_exec_status", "execution_id", "status"),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("executions.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(sa.String(100))
    call_seq: Mapped[int]
    llm_tool_call_id: Mapped[str | None] = mapped_column(sa.String(120))
    server_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("mcp_servers.id", ondelete="SET NULL"))
    tool_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("mcp_tools.id", ondelete="SET NULL"))
    tool_name: Mapped[str] = mapped_column(sa.String(200))
    namespaced_name: Mapped[str] = mapped_column(sa.String(300))
    arguments: Mapped[dict[str, Any]] = mapped_column(default=dict)
    idempotency_key: Mapped[str] = mapped_column(sa.String(200))
    status: Mapped[ToolCallStatus] = mapped_column(enum_col(ToolCallStatus, name="tool_call_status"))
    policy_decision: Mapped[dict[str, Any] | None]
    # Safe to re-run without a human: read-only and not marked destructive (SnapshotTool.safe_to_rerun).
    is_read_only: Mapped[bool] = mapped_column(default=False)
    result: Mapped[dict[str, Any] | None]
    error: Mapped[dict[str, Any] | None]
    duration_ms: Mapped[int | None]
    attempt: Mapped[int] = mapped_column(default=0)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class Approval(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        sa.Index("ix_approvals_ws_status", "workspace_id", "status", "created_at"),
        sa.Index(
            "uq_approvals_pending_tool_call",
            "tool_call_id",
            unique=True,
            postgresql_where=sa.text("status = 'pending'"),
        ),
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("executions.id", ondelete="CASCADE"), index=True)
    node_id: Mapped[str] = mapped_column(sa.String(100))
    kind: Mapped[ApprovalKind] = mapped_column(enum_col(ApprovalKind, name="approval_kind"))
    tool_call_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("tool_calls.id", ondelete="CASCADE"))
    status: Mapped[ApprovalStatus] = mapped_column(enum_col(ApprovalStatus, name="approval_status"))
    title: Mapped[str] = mapped_column(sa.String(300))
    summary: Mapped[str | None] = mapped_column(sa.Text)
    risk_level: Mapped[str | None] = mapped_column(sa.String(20))
    reasons: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    original_arguments: Mapped[dict[str, Any] | None]
    edited_arguments: Mapped[dict[str, Any] | None]
    payload: Mapped[dict[str, Any] | None] = mapped_column(comment="data under review / context")
    decision: Mapped[str | None] = mapped_column(sa.String(40))
    decided_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(sa.Text)
    feedback: Mapped[str | None] = mapped_column(sa.Text)
    resolution: Mapped[dict[str, Any] | None]
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("approvals.id", ondelete="SET NULL"))
    expires_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), index=True)
    resumed: Mapped[bool] = mapped_column(default=False, comment="decision consumed by the worker")


class LLMUsage(IdMixin, WorkspaceScoped, Base):
    __tablename__ = "llm_usage"
    __table_args__ = (sa.Index("ix_llm_usage_ws_created", "workspace_id", "created_at"),)

    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("executions.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str | None] = mapped_column(sa.String(100))
    provider_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("llm_providers.id", ondelete="SET NULL"))
    provider: Mapped[str] = mapped_column(sa.String(40))
    model: Mapped[str] = mapped_column(sa.String(200))
    input_tokens: Mapped[int] = mapped_column(default=0)
    output_tokens: Mapped[int] = mapped_column(default=0)
    total_tokens: Mapped[int] = mapped_column(default=0)
    estimated_cost: Mapped[Decimal] = mapped_column(sa.Numeric(14, 6), default=Decimal(0))
    latency_ms: Mapped[int] = mapped_column(default=0)
    stop_reason: Mapped[str | None] = mapped_column(sa.String(40))
    summary: Mapped[str | None] = mapped_column(sa.Text, comment="short output summary, never chain-of-thought")
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())


class DurableTimer(IdMixin, TimestampMixin, Base):
    __tablename__ = "durable_timers"
    __table_args__ = (sa.UniqueConstraint("execution_id", "node_id"),)

    execution_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("executions.id", ondelete="CASCADE"))
    node_id: Mapped[str] = mapped_column(sa.String(100))
    wake_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    fired_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class AuditEvent(IdMixin, Base):
    """Append-only: UPDATE/DELETE are rejected by a trigger (see migration)."""

    __tablename__ = "audit_events"
    __table_args__ = (
        sa.Index("ix_audit_ws_created", "workspace_id", "created_at"),
        sa.Index("ix_audit_entity", "entity_type", "entity_id"),
    )

    workspace_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("workspaces.id", ondelete="SET NULL"))
    actor_type: Mapped[str] = mapped_column(sa.String(20), comment="user | system | worker | scheduler")
    actor_id: Mapped[str | None] = mapped_column(sa.String(120))
    actor_label: Mapped[str | None] = mapped_column(sa.String(320))
    event_type: Mapped[str] = mapped_column(sa.String(60), index=True)
    entity_type: Mapped[str | None] = mapped_column(sa.String(60))
    entity_id: Mapped[str | None] = mapped_column(sa.String(120))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    request_id: Mapped[str | None] = mapped_column(sa.String(64))
    ip: Mapped[str | None] = mapped_column(sa.String(64))
    created_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), server_default=sa.func.now())
