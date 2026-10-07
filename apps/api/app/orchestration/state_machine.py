"""Execution and tool-call state machines: the single definition of allowed transitions."""

from __future__ import annotations

from app.core.enums import ExecutionStatus as E
from app.core.enums import ToolCallStatus as T
from app.core.errors import IllegalTransition

EXECUTION_TRANSITIONS: dict[E, frozenset[E]] = {
    E.created: frozenset({E.queued, E.cancelled}),
    E.queued: frozenset({E.running, E.cancelled, E.failed}),
    E.running: frozenset(
        {
            E.waiting_for_tool,
            E.waiting_for_timer,
            E.paused_for_review,
            E.paused,
            E.completed,
            E.failed,
            E.cancelled,
            E.queued,
        }
    ),
    E.waiting_for_tool: frozenset({E.running, E.failed, E.cancelled, E.queued}),
    E.waiting_for_timer: frozenset({E.resuming, E.cancelled}),
    E.paused_for_review: frozenset({E.resuming, E.cancelled}),
    E.paused: frozenset({E.resuming, E.cancelled}),
    E.resuming: frozenset({E.running, E.cancelled, E.failed, E.queued}),
    E.failed: frozenset({E.resuming}),
    E.completed: frozenset(),
    E.cancelled: frozenset(),
}

TOOL_CALL_TRANSITIONS: dict[T, frozenset[T]] = {
    T.pending: frozenset({T.awaiting_approval, T.executing, T.rejected, T.failed, T.cancelled}),
    T.awaiting_approval: frozenset({T.approved, T.rejected, T.cancelled}),
    T.approved: frozenset({T.executing, T.cancelled}),
    T.executing: frozenset({T.completed, T.failed, T.timeout, T.outcome_unknown, T.pending}),
    T.failed: frozenset({T.executing}),
    T.timeout: frozenset({T.executing}),
    T.outcome_unknown: frozenset({T.completed, T.failed, T.executing}),
    T.completed: frozenset(),
    T.rejected: frozenset(),
    T.cancelled: frozenset(),
}


def can_transition_execution(current: E, new: E) -> bool:
    return new in EXECUTION_TRANSITIONS[current]


def check_execution(current: E, new: E) -> None:
    if not can_transition_execution(current, new):
        raise IllegalTransition(
            f"Execution cannot move from {current.value} to {new.value}",
            details={"from": current.value, "to": new.value},
        )


def check_tool_call(current: T, new: T) -> None:
    if new not in TOOL_CALL_TRANSITIONS[current]:
        raise IllegalTransition(
            f"Tool call cannot move from {current.value} to {new.value}",
            details={"from": current.value, "to": new.value},
        )


def sources_for(new: E) -> list[E]:
    """All states from which `new` is reachable (for compare-and-set UPDATE ... WHERE status IN)."""
    return [s for s, targets in EXECUTION_TRANSITIONS.items() if new in targets]
