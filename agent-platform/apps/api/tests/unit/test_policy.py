"""ToolPolicyEngine rule order and outcomes."""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.core.enums import ErrorCode, PolicyDecision, RiskLevel, Role
from app.orchestration.snapshot import SnapshotTool
from app.tools.policy import PolicyContext, ToolPolicyEngine, Verdict

NAME = "demo_jobs__submit_proposal"
HASH = "a" * 64


def tool(**overrides: Any) -> SnapshotTool:
    values: dict[str, Any] = {
        "tool_id": uuid.uuid4(),
        "server_id": uuid.uuid4(),
        "server_slug": "demo_jobs",
        "name": "submit_proposal",
        "namespaced_name": NAME,
        "input_schema": {"type": "object"},
        "schema_hash": HASH,
        "is_enabled": True,
        "is_read_only": False,
        "is_destructive": False,
        "requires_approval": False,
        "risk_level": RiskLevel.medium,
    }
    return SnapshotTool(**{**values, **overrides})


def ctx(**overrides: Any) -> PolicyContext:
    values: dict[str, Any] = {
        "execution_id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "node_id": "draft",
        "allowlist": frozenset({NAME}),
        "started_by_role": Role.operator,
        "live_schema_hash": HASH,
    }
    return PolicyContext(**{**values, **overrides})


ENGINE = ToolPolicyEngine()


def test_allow_when_everything_passes() -> None:
    decision = ENGINE.evaluate(NAME, tool(), ctx())
    assert decision.decision == PolicyDecision.allow
    assert decision.risk_level == RiskLevel.medium and decision.code is None
    assert decision.to_dict() == {
        "decision": "allow",
        "reasons": ["All policies passed"],
        "risk_level": "medium",
        "code": None,
    }


@pytest.mark.parametrize(
    ("snapshot_tool", "context", "code"),
    [
        (None, ctx(), ErrorCode.tool_not_enabled),
        (tool(is_enabled=False), ctx(), ErrorCode.tool_not_enabled),
        (tool(), ctx(allowlist=frozenset({"other__tool"})), ErrorCode.tool_not_allowed),
        (tool(), ctx(started_by_role=Role.viewer), ErrorCode.forbidden),
        (tool(), ctx(live_schema_hash="b" * 64), ErrorCode.tool_schema_changed),
    ],
)
def test_deny_rules(snapshot_tool: SnapshotTool | None, context: PolicyContext, code: ErrorCode) -> None:
    decision = ENGINE.evaluate(NAME, snapshot_tool, context)
    assert decision.decision == PolicyDecision.deny
    assert decision.code == code
    assert len(decision.reasons) == 1


def test_deny_order_first_failing_rule_wins() -> None:
    # Disabled AND outside the allow-list AND schema drift: the earliest rule decides.
    decision = ENGINE.evaluate(
        NAME,
        tool(is_enabled=False, requires_approval=True),
        ctx(allowlist=frozenset(), live_schema_hash="c" * 64, started_by_role=Role.viewer),
    )
    assert decision.code == ErrorCode.tool_not_enabled
    decision = ENGINE.evaluate(
        NAME, tool(requires_approval=True), ctx(allowlist=frozenset(), live_schema_hash="c" * 64)
    )
    assert decision.code == ErrorCode.tool_not_allowed
    # A deny beats a pending approval requirement.
    decision = ENGINE.evaluate(NAME, tool(requires_approval=True, is_destructive=True), ctx(live_schema_hash="c" * 64))
    assert decision.decision == PolicyDecision.deny and decision.code == ErrorCode.tool_schema_changed


def test_unknown_live_hash_and_no_allowlist_do_not_deny() -> None:
    assert ENGINE.evaluate(NAME, tool(), ctx(live_schema_hash=None, allowlist=None)).decision == PolicyDecision.allow
    assert ENGINE.evaluate(NAME, tool(), ctx(started_by_role=None)).decision == PolicyDecision.allow


@pytest.mark.parametrize(
    ("flags", "reasons"),
    [
        ({"requires_approval": True}, ["Tool is configured to require approval"]),
        ({"is_destructive": True}, ["Tool is marked destructive"]),
        (
            {"requires_approval": True, "is_destructive": True, "risk_level": RiskLevel.high},
            ["Tool is configured to require approval"],
        ),
    ],
)
def test_approval_required(flags: dict[str, Any], reasons: list[str]) -> None:
    decision = ENGINE.evaluate(NAME, tool(**flags), ctx())
    assert decision.decision == PolicyDecision.require_approval
    assert decision.reasons == reasons
    assert decision.risk_level == flags.get("risk_level", RiskLevel.medium)


def test_missing_tool_is_high_risk() -> None:
    assert ENGINE.evaluate(NAME, None, ctx()).risk_level == RiskLevel.high


def test_custom_policies_compose() -> None:
    class AlwaysReview:
        name = "always_review"

        def evaluate(self, name: str, t: SnapshotTool | None, c: PolicyContext) -> Verdict | None:
            return Verdict(PolicyDecision.require_approval, "Second opinion")

    engine = ToolPolicyEngine((*ToolPolicyEngine().policies, AlwaysReview()))
    decision = engine.evaluate(NAME, tool(is_destructive=True), ctx())
    assert decision.reasons == ["Tool is marked destructive", "Second opinion"]
