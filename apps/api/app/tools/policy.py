"""ToolPolicyEngine: composable rules evaluated on every tool call.

Order: tool exists -> enabled in snapshot -> in node allow-list -> caller permission ->
schema hash matches the live server -> approval requirement. A `deny` stops evaluation;
`require_approval` reasons accumulate. New dimensions (spend caps, domains, time windows)
are new `Policy` classes added to `DEFAULT_POLICIES`, not edits to existing ones.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.core.enums import ROLE_RANK, ErrorCode, PolicyDecision, RiskLevel, Role
from app.orchestration.snapshot import SnapshotTool


@dataclass(frozen=True)
class PolicyContext:
    execution_id: uuid.UUID
    workspace_id: uuid.UUID
    node_id: str
    allowlist: frozenset[str] | None
    started_by_role: Role | None
    live_schema_hash: str | None
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Verdict:
    decision: PolicyDecision
    reason: str
    code: ErrorCode | None = None


@dataclass
class Decision:
    decision: PolicyDecision
    reasons: list[str]
    risk_level: RiskLevel
    code: ErrorCode | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reasons": self.reasons,
            "risk_level": self.risk_level.value,
            "code": self.code.value if self.code else None,
        }


class Policy(Protocol):
    name: str

    def evaluate(self, name: str, tool: SnapshotTool | None, ctx: PolicyContext) -> Verdict | None: ...


class ToolExists:
    name = "tool_exists"

    def evaluate(self, name: str, tool: SnapshotTool | None, ctx: PolicyContext) -> Verdict | None:
        if tool is None:
            return Verdict(
                PolicyDecision.deny, f"Tool {name} is not available in this execution", ErrorCode.tool_not_enabled
            )
        return None


class ToolEnabled:
    name = "tool_enabled"

    def evaluate(self, name: str, tool: SnapshotTool | None, ctx: PolicyContext) -> Verdict | None:
        if tool is not None and not tool.is_enabled:
            return Verdict(PolicyDecision.deny, f"Tool {name} is disabled", ErrorCode.tool_not_enabled)
        return None


class InAllowList:
    name = "allow_list"

    def evaluate(self, name: str, tool: SnapshotTool | None, ctx: PolicyContext) -> Verdict | None:
        if ctx.allowlist is not None and name not in ctx.allowlist:
            return Verdict(
                PolicyDecision.deny, f"Tool {name} is not in this node's allow-list", ErrorCode.tool_not_allowed
            )
        return None


class CallerPermission:
    """Executions run with the authority of whoever started them (scheduled runs: the schedule owner)."""

    name = "caller_permission"

    def evaluate(self, name: str, tool: SnapshotTool | None, ctx: PolicyContext) -> Verdict | None:
        role = ctx.started_by_role
        if role is not None and ROLE_RANK[role] < ROLE_RANK[Role.operator]:
            return Verdict(PolicyDecision.deny, "Executions started by a viewer cannot call tools", ErrorCode.forbidden)
        return None


class SchemaUnchanged:
    name = "schema_hash"

    def evaluate(self, name: str, tool: SnapshotTool | None, ctx: PolicyContext) -> Verdict | None:
        if tool is not None and ctx.live_schema_hash is not None and ctx.live_schema_hash != tool.schema_hash:
            return Verdict(
                PolicyDecision.deny,
                f"The live schema of {name} differs from the one this execution was started with",
                ErrorCode.tool_schema_changed,
            )
        return None


class ApprovalRequired:
    name = "approval_required"

    def evaluate(self, name: str, tool: SnapshotTool | None, ctx: PolicyContext) -> Verdict | None:
        if tool is None:
            return None
        if tool.requires_approval:
            return Verdict(PolicyDecision.require_approval, "Tool is configured to require approval")
        if tool.is_destructive:
            return Verdict(PolicyDecision.require_approval, "Tool is marked destructive")
        return None


DEFAULT_POLICIES: tuple[Policy, ...] = (
    ToolExists(),
    ToolEnabled(),
    InAllowList(),
    CallerPermission(),
    SchemaUnchanged(),
    ApprovalRequired(),
)


class ToolPolicyEngine:
    def __init__(self, policies: tuple[Policy, ...] = DEFAULT_POLICIES) -> None:
        self.policies = policies

    def evaluate(self, name: str, tool: SnapshotTool | None, ctx: PolicyContext) -> Decision:
        risk = tool.risk_level if tool is not None else RiskLevel.high
        reasons: list[str] = []
        needs_approval = False
        for policy in self.policies:
            verdict = policy.evaluate(name, tool, ctx)
            if verdict is None:
                continue
            if verdict.decision == PolicyDecision.deny:
                return Decision(PolicyDecision.deny, [verdict.reason], risk, verdict.code)
            if verdict.decision == PolicyDecision.require_approval:
                needs_approval = True
                reasons.append(verdict.reason)
        if needs_approval:
            return Decision(PolicyDecision.require_approval, reasons, risk)
        return Decision(PolicyDecision.allow, ["All policies passed"], risk)
