"""Every status, type and code used across modules. No magic strings elsewhere."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    owner = "owner"
    operator = "operator"
    viewer = "viewer"


ROLE_RANK: dict[Role, int] = {Role.viewer: 0, Role.operator: 1, Role.owner: 2}


class ProviderType(StrEnum):
    openai = "openai"
    anthropic = "anthropic"
    ollama = "ollama"
    gemini = "gemini"
    fake = "fake"


class TransportType(StrEnum):
    stdio = "stdio"
    streamable_http = "streamable_http"
    sse_legacy = "sse_legacy"


class ServerStatus(StrEnum):
    disconnected = "disconnected"
    connecting = "connecting"
    initializing = "initializing"
    discovering = "discovering"
    ready = "ready"
    reconnecting = "reconnecting"
    failed = "failed"


class IsolationMode(StrEnum):
    shared = "shared"
    per_execution = "per_execution"


class RiskLevel(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class NodeType(StrEnum):
    trigger = "trigger"
    llm = "llm"
    agent = "agent"
    mcp_tool = "mcp_tool"
    condition = "condition"
    transform = "transform"
    human_approval = "human_approval"
    notification = "notification"
    delay = "delay"
    end = "end"


class ExecutionStatus(StrEnum):
    created = "created"
    queued = "queued"
    running = "running"
    waiting_for_tool = "waiting_for_tool"
    waiting_for_timer = "waiting_for_timer"
    paused_for_review = "paused_for_review"
    paused = "paused"
    resuming = "resuming"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


TERMINAL_EXECUTION_STATUSES = frozenset({ExecutionStatus.completed, ExecutionStatus.cancelled})
ACTIVE_EXECUTION_STATUSES = frozenset(
    {
        ExecutionStatus.queued,
        ExecutionStatus.running,
        ExecutionStatus.waiting_for_tool,
        ExecutionStatus.resuming,
    }
)


class NodeStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"
    waiting = "waiting"
    retrying = "retrying"
    cancelled = "cancelled"


class ToolCallStatus(StrEnum):
    pending = "pending"
    awaiting_approval = "awaiting_approval"
    approved = "approved"
    executing = "executing"
    completed = "completed"
    failed = "failed"
    rejected = "rejected"
    cancelled = "cancelled"
    timeout = "timeout"
    outcome_unknown = "outcome_unknown"


class ApprovalKind(StrEnum):
    tool_call = "tool_call"
    data_review = "data_review"
    outcome_unknown = "outcome_unknown"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    superseded = "superseded"
    expired = "expired"


class DecisionAction(StrEnum):
    approve = "approve"
    edit = "edit"
    reject = "reject"
    regenerate = "regenerate"
    mark_succeeded = "mark_succeeded"
    mark_failed = "mark_failed"
    rerun = "rerun"


class PolicyDecision(StrEnum):
    allow = "allow"
    deny = "deny"
    require_approval = "require_approval"


class TriggerKind(StrEnum):
    manual = "manual"
    schedule = "schedule"
    webhook = "webhook"
    restart = "restart"


class ScheduleKind(StrEnum):
    interval = "interval"
    daily = "daily"
    cron = "cron"


class OverlapPolicy(StrEnum):
    skip = "skip"
    queue = "queue"


class NotificationChannelType(StrEnum):
    webhook = "webhook"
    slack = "slack"
    discord = "discord"


class InterruptKind(StrEnum):
    approval = "approval"
    operator_pause = "operator_pause"
    timer = "timer"


class EventType(StrEnum):
    execution_created = "execution.created"
    execution_started = "execution.started"
    execution_paused = "execution.paused"
    execution_resumed = "execution.resumed"
    execution_completed = "execution.completed"
    execution_failed = "execution.failed"
    execution_cancelled = "execution.cancelled"
    node_started = "node.started"
    node_completed = "node.completed"
    node_failed = "node.failed"
    node_retrying = "node.retrying"
    llm_requested = "llm.requested"
    llm_completed = "llm.completed"
    tool_requested = "tool.requested"
    tool_awaiting_approval = "tool.awaiting_approval"
    tool_approved = "tool.approved"
    tool_rejected = "tool.rejected"
    tool_executing = "tool.executing"
    tool_completed = "tool.completed"
    tool_failed = "tool.failed"
    approval_created = "approval.created"
    approval_decided = "approval.decided"
    mcp_server_status_changed = "mcp.server_status_changed"


class AuditEventType(StrEnum):
    auth_login = "auth.login"
    auth_login_failed = "auth.login_failed"
    auth_logout = "auth.logout"
    config_created = "config.created"
    config_updated = "config.updated"
    config_deleted = "config.deleted"
    secret_written = "secret.written"
    secret_accessed = "secret.accessed"
    secret_deleted = "secret.deleted"
    execution_started = "execution.started"
    execution_control = "execution.control"
    approval_decided = "approval.decided"
    tool_executed = "tool.executed"
    tool_denied = "tool.denied"
    member_updated = "member.updated"
    schedule_fired = "schedule.fired"


class ErrorCode(StrEnum):
    internal_error = "INTERNAL_ERROR"
    validation_error = "VALIDATION_ERROR"
    not_found = "NOT_FOUND"
    conflict = "CONFLICT"
    unauthenticated = "UNAUTHENTICATED"
    forbidden = "FORBIDDEN"
    csrf_failed = "CSRF_FAILED"
    rate_limited = "RATE_LIMITED"
    invalid_credentials = "INVALID_CREDENTIALS"
    illegal_transition = "ILLEGAL_TRANSITION"
    mcp_connection_failed = "MCP_CONNECTION_FAILED"
    mcp_tool_error = "MCP_TOOL_ERROR"
    tool_schema_changed = "TOOL_SCHEMA_CHANGED"
    tool_not_enabled = "TOOL_NOT_ENABLED"
    tool_not_allowed = "TOOL_NOT_ALLOWED"
    tool_arguments_invalid = "TOOL_ARGUMENTS_INVALID"
    tool_timeout = "TOOL_TIMEOUT"
    approval_already_decided = "APPROVAL_ALREADY_DECIDED"
    approval_not_allowed_in_map = "APPROVAL_NOT_ALLOWED_IN_MAP"
    pipeline_invalid = "PIPELINE_INVALID"
    template_error = "TEMPLATE_ERROR"
    expression_error = "EXPRESSION_ERROR"
    llm_rate_limited = "LLM_RATE_LIMITED"
    llm_timeout = "LLM_TIMEOUT"
    llm_unavailable = "LLM_PROVIDER_UNAVAILABLE"
    llm_auth_failed = "LLM_AUTH_FAILED"
    llm_invalid_request = "LLM_INVALID_REQUEST"
    llm_context_too_long = "LLM_CONTEXT_TOO_LONG"
    llm_content_filtered = "LLM_CONTENT_FILTERED"
    ssrf_blocked = "OUTBOUND_URL_BLOCKED"
    secret_not_found = "SECRET_NOT_FOUND"
    execution_cancelled = "EXECUTION_CANCELLED"
    retry_budget_exhausted = "RETRY_BUDGET_EXHAUSTED"
    limit_exceeded = "LIMIT_EXCEEDED"
