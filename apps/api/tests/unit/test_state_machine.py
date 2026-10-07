"""Execution and tool-call state machines."""

from __future__ import annotations

import pytest

from app.core.enums import ExecutionStatus as E
from app.core.enums import ToolCallStatus as T
from app.core.errors import IllegalTransition
from app.orchestration.state_machine import (
    EXECUTION_TRANSITIONS,
    TOOL_CALL_TRANSITIONS,
    can_transition_execution,
    check_execution,
    check_tool_call,
    sources_for,
)

LEGAL_EXECUTION = [
    (E.created, E.queued), (E.queued, E.running), (E.running, E.paused_for_review), (E.running, E.queued),
    (E.paused_for_review, E.resuming), (E.resuming, E.running), (E.running, E.completed),
    (E.waiting_for_timer, E.resuming), (E.failed, E.resuming), (E.paused, E.cancelled),
]
ILLEGAL_EXECUTION = [
    (E.completed, E.running), (E.cancelled, E.resuming), (E.paused_for_review, E.running),
    (E.queued, E.completed), (E.created, E.running), (E.failed, E.completed), (E.waiting_for_timer, E.running),
]


@pytest.mark.parametrize(("current", "new"), LEGAL_EXECUTION)
def test_legal_execution_transitions(current: E, new: E) -> None:
    assert can_transition_execution(current, new)
    check_execution(current, new)


@pytest.mark.parametrize(("current", "new"), ILLEGAL_EXECUTION)
def test_illegal_execution_transitions(current: E, new: E) -> None:
    assert not can_transition_execution(current, new)
    with pytest.raises(IllegalTransition) as info:
        check_execution(current, new)
    assert info.value.details == {"from": current.value, "to": new.value}
    assert info.value.http_status == 409


def test_terminal_states_and_completeness() -> None:
    assert set(EXECUTION_TRANSITIONS) == set(E)
    assert set(TOOL_CALL_TRANSITIONS) == set(T)
    assert EXECUTION_TRANSITIONS[E.completed] == frozenset()
    assert EXECUTION_TRANSITIONS[E.cancelled] == frozenset()
    for terminal in (T.completed, T.rejected, T.cancelled):
        assert TOOL_CALL_TRANSITIONS[terminal] == frozenset()


def test_sources_for_cas_updates() -> None:
    assert set(sources_for(E.resuming)) == {E.waiting_for_timer, E.paused_for_review, E.paused, E.failed}
    assert set(sources_for(E.completed)) == {E.running}
    assert E.completed not in sources_for(E.cancelled)


@pytest.mark.parametrize(
    ("current", "new", "legal"),
    [
        (T.pending, T.awaiting_approval, True), (T.awaiting_approval, T.approved, True),
        (T.approved, T.executing, True), (T.executing, T.outcome_unknown, True),
        (T.outcome_unknown, T.completed, True), (T.outcome_unknown, T.executing, True),
        (T.awaiting_approval, T.executing, False), (T.pending, T.completed, False),
        (T.completed, T.executing, False), (T.rejected, T.approved, False), (T.cancelled, T.pending, False),
    ],
)
def test_tool_call_transitions(current: T, new: T, legal: bool) -> None:
    if legal:
        check_tool_call(current, new)
    else:
        with pytest.raises(IllegalTransition):
            check_tool_call(current, new)
