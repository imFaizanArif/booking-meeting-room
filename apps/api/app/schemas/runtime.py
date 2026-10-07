"""DTOs for pipelines, executions, approvals, schedules, audit and the dashboard."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import Field

from app.core.enums import (
    ApprovalKind,
    ApprovalStatus,
    DecisionAction,
    ExecutionStatus,
    NodeStatus,
    NodeType,
    OverlapPolicy,
    ScheduleKind,
    ServerStatus,
    ToolCallStatus,
    TriggerKind,
)
from app.schemas.common import ORM, Schema
from app.schemas.pipeline_graph import PipelineGraph

# ---- pipelines ------------------------------------------------------------------------------


class PipelineIn(Schema):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    graph: PipelineGraph | None = None


class PipelinePatch(Schema):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_archived: bool | None = None


class PipelineVersionIn(Schema):
    graph: dict[str, Any] = Field(description="PipelineGraph JSON; validated server-side with node-level errors")
    change_note: str | None = Field(default=None, max_length=500)


class GraphIssueOut(Schema):
    message: str
    node_id: str | None = None
    edge_id: str | None = None
    severity: str = "error"


class ValidationOut(Schema):
    ok: bool
    issues: list[GraphIssueOut]


class PipelineVersionOut(ORM):
    id: uuid.UUID
    pipeline_id: uuid.UUID
    version: int
    graph: PipelineGraph
    graph_hash: str
    change_note: str | None
    created_by: uuid.UUID | None
    created_at: datetime


class PipelineVersionSummary(ORM):
    id: uuid.UUID
    version: int
    graph_hash: str
    change_note: str | None
    created_at: datetime


class PipelineOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    latest_version_id: uuid.UUID | None
    latest_version_number: int
    is_archived: bool
    node_count: int = 0
    last_execution_status: ExecutionStatus | None = None
    last_execution_at: datetime | None = None
    schedule_count: int = 0
    created_at: datetime
    updated_at: datetime


class PipelineDetail(PipelineOut):
    latest: PipelineVersionOut | None
    versions: list[PipelineVersionSummary]


class RunIn(Schema):
    input: dict[str, Any] = Field(default_factory=dict)
    version: int | None = None


class NodeTypeOut(Schema):
    type: NodeType
    label: str
    description: str
    config_schema: dict[str, Any]
    mappable: bool


# ---- executions ------------------------------------------------------------------------------


class ExecutionOut(ORM):
    id: uuid.UUID
    pipeline_id: uuid.UUID
    pipeline_name: str = ""
    pipeline_version_id: uuid.UUID
    pipeline_version: int = 0
    trigger: TriggerKind
    status: ExecutionStatus
    input: dict[str, Any]
    output: dict[str, Any] | None
    error: dict[str, Any] | None
    total_tokens: int
    estimated_cost: Decimal
    retries_used: int
    cancel_requested: bool
    pause_requested: bool
    restarted_from_id: uuid.UUID | None
    schedule_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExecutionNodeOut(ORM):
    node_id: str
    node_type: NodeType
    name: str
    status: NodeStatus
    attempts: int
    input_summary: dict[str, Any] | None
    output_summary: dict[str, Any] | None
    error: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None


class ToolCallOut(ORM):
    id: uuid.UUID
    execution_id: uuid.UUID
    node_id: str
    call_seq: int
    server_id: uuid.UUID | None
    tool_name: str
    namespaced_name: str
    arguments: dict[str, Any]
    idempotency_key: str
    status: ToolCallStatus
    policy_decision: dict[str, Any] | None
    is_read_only: bool
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    duration_ms: int | None
    attempt: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class LLMUsageOut(ORM):
    id: uuid.UUID
    node_id: str | None
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost: Decimal
    latency_ms: int
    stop_reason: str | None
    summary: str | None
    created_at: datetime


class ApprovalOut(ORM):
    id: uuid.UUID
    execution_id: uuid.UUID
    node_id: str
    kind: ApprovalKind
    tool_call_id: uuid.UUID | None
    status: ApprovalStatus
    title: str
    summary: str | None
    risk_level: str | None
    reasons: list[str]
    original_arguments: dict[str, Any] | None
    edited_arguments: dict[str, Any] | None
    payload: dict[str, Any] | None
    decision: str | None
    decided_by: uuid.UUID | None
    decided_by_email: str | None = None
    decided_at: datetime | None
    reason: str | None
    feedback: str | None
    resolution: dict[str, Any] | None
    superseded_by: uuid.UUID | None
    expires_at: datetime | None
    created_at: datetime
    pipeline_name: str = ""
    tool_name: str | None = None
    server_slug: str | None = None


class ApprovalDetail(ApprovalOut):
    tool_call: ToolCallOut | None = None
    input_schema: dict[str, Any] | None = None
    context: list[dict[str, Any]] = Field(default_factory=list, description="Recent agent steps (no reasoning)")
    history: list[ApprovalOut] = Field(default_factory=list, description="Regenerate chain")


class DecisionIn(Schema):
    action: DecisionAction
    edited_arguments: dict[str, Any] | None = None
    edited_data: Any = None
    reason: str | None = Field(default=None, max_length=4000)
    feedback: str | None = Field(default=None, max_length=4000)
    result: Any = Field(default=None, description="mark_succeeded: what the call returned, if known")
    confirm: bool = False


class ExecutionDetail(Schema):
    execution: ExecutionOut
    nodes: list[ExecutionNodeOut]
    tool_calls: list[ToolCallOut]
    usage: list[LLMUsageOut]
    approvals: list[ApprovalOut]
    graph: PipelineGraph
    snapshot: dict[str, Any]


class ControlIn(Schema):
    action: str = Field(pattern=r"^(pause|resume|cancel|retry)$")


# ---- schedules --------------------------------------------------------------------------------


class ScheduleIn(Schema):
    pipeline_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    kind: ScheduleKind
    cron: str | None = None
    interval_seconds: int | None = None
    daily_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    timezone: str = "UTC"
    input: dict[str, Any] = Field(default_factory=dict)
    overlap_policy: OverlapPolicy = OverlapPolicy.skip
    is_active: bool = True


class ScheduleOut(ORM):
    id: uuid.UUID
    pipeline_id: uuid.UUID
    pipeline_name: str = ""
    name: str
    kind: ScheduleKind
    cron: str | None
    interval_seconds: int | None
    daily_time: str | None
    timezone: str
    input: dict[str, Any]
    overlap_policy: OverlapPolicy
    is_active: bool
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime


class ScheduleFireOut(ORM):
    id: uuid.UUID
    fire_at: datetime
    execution_id: uuid.UUID | None
    outcome: str
    fired_by: str
    created_at: datetime


# ---- audit & dashboard --------------------------------------------------------------------------


class AuditOut(ORM):
    id: uuid.UUID
    actor_type: str
    actor_id: str | None
    actor_label: str | None
    event_type: str
    entity_type: str | None
    entity_id: str | None
    execution_id: uuid.UUID | None
    payload: dict[str, Any]
    request_id: str | None
    ip: str | None
    created_at: datetime


class DashboardServer(Schema):
    id: uuid.UUID
    name: str
    status: ServerStatus
    status_message: str | None


class DashboardSchedule(Schema):
    id: uuid.UUID
    name: str
    pipeline_name: str
    next_run_at: datetime | None


class DashboardOut(Schema):
    running: list[ExecutionOut]
    pending_approvals: list[ApprovalOut]
    unhealthy_servers: list[DashboardServer]
    next_runs: list[DashboardSchedule]
    recent_failures: list[ExecutionOut]
    cost_24h: Decimal
    tokens_24h: int
    executions_24h: int
    status_counts_24h: dict[str, int]
