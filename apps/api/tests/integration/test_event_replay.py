"""execution_events carry a gap-free sequence per execution."""

from __future__ import annotations

from sqlalchemy import select

from app.core.enums import DecisionAction, EventType, ExecutionStatus
from app.db.session import session_scope
from app.models import ExecutionEvent
from app.services.context import AuthContext
from tests.conftest import RunnerFactory
from tests.helpers import db_execution, decide_as, event_seqs, pending_approval, start_demo


async def test_sequence_is_gap_free_across_pause_and_resume(
    operator_ctx: AuthContext, runners: RunnerFactory,
) -> None:
    execution_id = await start_demo(operator_ctx)
    await runners.new().run(execution_id)
    paused_seqs = await event_seqs(execution_id)
    assert paused_seqs == list(range(1, len(paused_seqs) + 1))

    await decide_as(operator_ctx, (await pending_approval(execution_id)).id, DecisionAction.approve)
    assert await runners.new().run(execution_id) == ExecutionStatus.completed
    seqs = await event_seqs(execution_id)
    assert seqs == list(range(1, len(seqs) + 1))
    assert len(seqs) > len(paused_seqs)
    assert (await db_execution(execution_id)).last_event_seq == len(seqs)

    async with session_scope() as session:
        types = list((await session.scalars(select(ExecutionEvent.type).where(
            ExecutionEvent.execution_id == execution_id).order_by(ExecutionEvent.seq))).all())
    assert types[0] == EventType.execution_created
    assert types[-1] == EventType.execution_completed
    for expected in (EventType.approval_created, EventType.approval_decided, EventType.tool_awaiting_approval,
                     EventType.tool_approved, EventType.execution_paused):
        assert expected in types
