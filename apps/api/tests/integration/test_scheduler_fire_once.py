"""Two scheduler instances racing on one due schedule fire it exactly once."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import timedelta

import pytest
from sqlalchemy import delete, select

from app.core.enums import ExecutionStatus, OverlapPolicy, ScheduleKind, TriggerKind
from app.core.time import utcnow
from app.db.session import session_scope
from app.models import Execution, Schedule, ScheduleFire
from app.scheduler.sweeps import fire_due_schedules
from app.services.context import AuthContext
from app.workers.queue import Job
from tests.conftest import FakeQueue
from tests.helpers import DEMO_INPUT, demo_pipeline_id


@pytest.fixture
async def due_schedule(operator_ctx: AuthContext) -> AsyncIterator[Schedule]:
    async with session_scope() as session:
        schedule = Schedule(
            workspace_id=operator_ctx.workspace_id,
            pipeline_id=await demo_pipeline_id(),
            name="race",
            kind=ScheduleKind.interval,
            interval_seconds=3600,
            timezone="UTC",
            input=DEMO_INPUT,
            overlap_policy=OverlapPolicy.queue,
            is_active=True,
            next_run_at=utcnow() - timedelta(seconds=1),
        )
        session.add(schedule)
    yield schedule
    async with session_scope() as session:
        await session.execute(delete(Schedule).where(Schedule.id == schedule.id))


async def test_concurrent_sweeps_fire_once(due_schedule: Schedule, fake_queue: FakeQueue) -> None:
    fired = await asyncio.gather(fire_due_schedules(fake_queue), fire_due_schedules(fake_queue))
    assert sum(fired) == 1

    async with session_scope() as session:
        fires = list(
            (await session.scalars(select(ScheduleFire).where(ScheduleFire.schedule_id == due_schedule.id))).all()
        )
        executions = list(
            (await session.scalars(select(Execution).where(Execution.schedule_id == due_schedule.id))).all()
        )
        schedule = await session.get(Schedule, due_schedule.id)
    assert [f.outcome for f in fires] == ["enqueued"]
    assert len(executions) == 1
    assert fires[0].execution_id == executions[0].id
    assert executions[0].trigger == TriggerKind.schedule
    assert executions[0].status == ExecutionStatus.queued
    assert fake_queue.of(Job.run_execution) == [(str(executions[0].id),)]
    assert schedule is not None and schedule.next_run_at is not None and schedule.next_run_at > utcnow()

    # Nothing is due any more.
    assert await fire_due_schedules(fake_queue) == 0


async def test_overlap_skip_records_skipped_fire(due_schedule: Schedule, fake_queue: FakeQueue) -> None:
    async with session_scope() as session:
        row = await session.get(Schedule, due_schedule.id)
        assert row is not None
        row.overlap_policy = OverlapPolicy.skip
    assert await fire_due_schedules(fake_queue) == 1
    async with session_scope() as session:
        row = await session.get(Schedule, due_schedule.id)
        assert row is not None
        row.next_run_at = utcnow() - timedelta(seconds=1)  # due again while the first run is still queued
    assert await fire_due_schedules(fake_queue) == 1
    async with session_scope() as session:
        outcomes = sorted(
            (
                await session.scalars(select(ScheduleFire.outcome).where(ScheduleFire.schedule_id == due_schedule.id))
            ).all()
        )
    assert outcomes == ["enqueued", "skipped_overlap"]


async def test_many_concurrent_sweeps_fire_each_due_schedule_once(
    operator_ctx: AuthContext,
    fake_queue: FakeQueue,
) -> None:
    pipeline_id = await demo_pipeline_id()
    async with session_scope() as session:
        schedules = [
            Schedule(
                workspace_id=operator_ctx.workspace_id,
                pipeline_id=pipeline_id,
                name=f"race-{i}",
                kind=ScheduleKind.interval,
                interval_seconds=3600,
                timezone="UTC",
                input=DEMO_INPUT,
                overlap_policy=OverlapPolicy.queue,
                is_active=True,
                next_run_at=utcnow() - timedelta(seconds=1 + i),
            )
            for i in range(5)
        ]
        session.add_all(schedules)
    ids = [s.id for s in schedules]
    try:
        fired = await asyncio.gather(*(fire_due_schedules(fake_queue, limit=2) for _ in range(6)))
        fired_later = await fire_due_schedules(fake_queue)  # anything skipped while locked
        assert sum(fired) + fired_later == len(ids)
        assert await fire_due_schedules(fake_queue) == 0
        async with session_scope() as session:
            fires = list((await session.scalars(select(ScheduleFire).where(ScheduleFire.schedule_id.in_(ids)))).all())
            executions = list((await session.scalars(select(Execution).where(Execution.schedule_id.in_(ids)))).all())
        assert sorted(f.schedule_id for f in fires) == sorted(ids)
        assert {f.outcome for f in fires} == {"enqueued"}
        assert sorted(e.schedule_id for e in executions if e.schedule_id) == sorted(ids)
        assert sorted(a[0] for a in fake_queue.of(Job.run_execution)) == sorted(str(e.id) for e in executions)
    finally:
        async with session_scope() as session:
            await session.execute(delete(Schedule).where(Schedule.id.in_(ids)))


async def test_occurrence_already_recorded_is_not_fired_again(due_schedule: Schedule, fake_queue: FakeQueue) -> None:
    """The unique (schedule_id, fire_at) key is the backstop when row locking alone is not enough."""
    async with session_scope() as session:
        row = await session.get(Schedule, due_schedule.id)
        assert row is not None and row.next_run_at is not None
        session.add(
            ScheduleFire(schedule_id=row.id, fire_at=row.next_run_at, outcome="enqueued", fired_by="another-instance")
        )
    assert await fire_due_schedules(fake_queue) == 0
    async with session_scope() as session:
        executions = (await session.scalars(select(Execution).where(Execution.schedule_id == due_schedule.id))).all()
        schedule = await session.get(Schedule, due_schedule.id)
    assert list(executions) == []
    assert fake_queue.of(Job.run_execution) == []
    assert schedule is not None and schedule.next_run_at is not None and schedule.next_run_at > utcnow()
