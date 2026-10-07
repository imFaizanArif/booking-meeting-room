"""Scheduler sweeps. Each is safe with several scheduler instances running.

* fire_due_schedules: rows are claimed with FOR UPDATE SKIP LOCKED and each occurrence is
  recorded in `schedule_fires` under a unique (schedule_id, fire_at) key, so an occurrence
  fires exactly once even if two instances race.
* recover_stale_executions: expired leases -> open tool calls resolved (read-only reset,
  others OUTCOME_UNKNOWN), execution re-queued and resumed from its checkpoint.
* wake_due_timers, expire_approvals: enqueue resumes; never run agent code.
"""

from __future__ import annotations

import socket
import uuid
from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit
from app.core.enums import (
    ACTIVE_EXECUTION_STATUSES,
    ApprovalStatus,
    AuditEventType,
    ExecutionStatus,
    OverlapPolicy,
    Role,
    ToolCallStatus,
    TriggerKind,
)
from app.core.logging import get_logger
from app.core.time import utcnow
from app.db.session import session_scope
from app.models import Approval, DurableTimer, Execution, Pipeline, PipelineVersion, Schedule, ScheduleFire, ToolCall
from app.scheduler.timing import next_fire
from app.services.context import SCHEDULER_ACTOR
from app.services.executions import dispatch_execution, prepare_execution
from app.workers.queue import Job, JobQueue, resume_job_id

log = get_logger(__name__)
INSTANCE = f"{socket.gethostname()}:{uuid.uuid4().hex[:6]}"


def _next(schedule: Schedule, after: datetime) -> datetime:
    return next_fire(
        schedule.kind,
        after=after,
        cron=schedule.cron,
        interval_seconds=schedule.interval_seconds,
        daily_time=schedule.daily_time,
        timezone=schedule.timezone,
        anchor=schedule.created_at,
    )


async def fire_due_schedules(queue: JobQueue, limit: int = 20) -> int:
    fired = 0
    now = utcnow()
    created: list[Execution] = []
    async with session_scope() as session:
        due = list(
            (
                await session.scalars(
                    select(Schedule)
                    .where(Schedule.is_active.is_(True), Schedule.next_run_at <= now)
                    .order_by(Schedule.next_run_at)
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for schedule in due:
            fire_at = schedule.next_run_at
            assert fire_at is not None
            schedule.next_run_at = _next(schedule, max(now, fire_at))
            try:
                async with session.begin_nested():
                    await session.execute(
                        insert(ScheduleFire).values(
                            id=uuid.uuid4(),
                            schedule_id=schedule.id,
                            fire_at=fire_at,
                            outcome="claimed",
                            fired_by=INSTANCE,
                        )
                    )
            except IntegrityError:
                continue  # another instance already fired this occurrence
            outcome, execution = await _fire(session, schedule)
            execution_id = execution.id if execution else None
            if execution is not None:
                created.append(execution)
            await session.execute(
                sa.update(ScheduleFire)
                .where(ScheduleFire.schedule_id == schedule.id, ScheduleFire.fire_at == fire_at)
                .values(outcome=outcome, execution_id=execution_id)
            )
            schedule.last_run_at = now
            fired += 1
    for execution in created:
        await dispatch_execution(execution, queue)
    return fired


async def _fire(session: AsyncSession, schedule: Schedule) -> tuple[str, Execution | None]:
    if schedule.overlap_policy == OverlapPolicy.skip:
        running = await session.scalar(
            select(sa.func.count())
            .select_from(Execution)
            .where(
                Execution.schedule_id == schedule.id,
                Execution.status.in_(
                    [
                        *ACTIVE_EXECUTION_STATUSES,
                        ExecutionStatus.paused_for_review,
                        ExecutionStatus.paused,
                        ExecutionStatus.waiting_for_timer,
                    ]
                ),
            )
        )
        if running:
            return "skipped_overlap", None
    pipeline = await session.get(Pipeline, schedule.pipeline_id)
    if pipeline is None or pipeline.latest_version_id is None:
        return "failed:no_version", None
    version = await session.get(PipelineVersion, pipeline.latest_version_id)
    assert version is not None
    try:
        async with session.begin_nested():
            execution = await prepare_execution(
                session,
                workspace_id=schedule.workspace_id,
                pipeline=pipeline,
                version=version,
                input=schedule.input or {},
                trigger=TriggerKind.schedule,
                actor=SCHEDULER_ACTOR,
                started_by_role=Role.operator,
                schedule_id=schedule.id,
            )
    except Exception as exc:  # noqa: BLE001 - a bad schedule must not stop the sweep
        log.warning("schedule_fire_failed", schedule=str(schedule.id), error=str(exc))
        return f"failed:{type(exc).__name__}"[:40], None
    await audit(
        session,
        event_type=AuditEventType.schedule_fired,
        actor=SCHEDULER_ACTOR,
        workspace_id=schedule.workspace_id,
        entity_type="schedule",
        entity_id=schedule.id,
        execution_id=execution.id,
        payload={"pipeline": pipeline.name},
    )
    return "enqueued", execution


async def recover_stale_executions(queue: JobQueue, stale_queued_after_s: int = 120) -> int:
    """Executions whose worker died (lease expired) are resumed from their last checkpoint."""
    now = utcnow()
    recovered = 0
    async with session_scope() as session:
        stale = list(
            (
                await session.scalars(
                    select(Execution)
                    .where(
                        or_(
                            and_(
                                Execution.status.in_(
                                    [
                                        ExecutionStatus.running,
                                        ExecutionStatus.waiting_for_tool,
                                        ExecutionStatus.resuming,
                                    ]
                                ),
                                Execution.lease_expires_at < now,
                            ),
                            and_(
                                Execution.status.in_([ExecutionStatus.queued, ExecutionStatus.resuming]),
                                Execution.lease_expires_at.is_(None),
                                Execution.updated_at < now - timedelta(seconds=stale_queued_after_s),
                            ),
                        )
                    )
                    .with_for_update(skip_locked=True)
                    .limit(50)
                )
            ).all()
        )
        for execution in stale:
            calls = list(
                (
                    await session.scalars(
                        select(ToolCall).where(
                            ToolCall.execution_id == execution.id, ToolCall.status == ToolCallStatus.executing
                        )
                    )
                ).all()
            )
            for call in calls:
                # Read-only calls can safely run again; anything else goes to a human.
                call.status = ToolCallStatus.pending if call.is_read_only else ToolCallStatus.outcome_unknown
            if execution.status in (ExecutionStatus.running, ExecutionStatus.waiting_for_tool):
                execution.status = ExecutionStatus.queued
            execution.lease_owner = None
            execution.lease_expires_at = None
            await audit(
                session,
                event_type=AuditEventType.execution_control,
                actor=SCHEDULER_ACTOR,
                workspace_id=execution.workspace_id,
                entity_type="execution",
                entity_id=execution.id,
                execution_id=execution.id,
                payload={"action": "recovered", "open_tool_calls": [str(c.id) for c in calls]},
            )
            recovered += 1
    for execution in stale:
        await queue.enqueue(Job.resume_execution, str(execution.id), job_id=resume_job_id(execution.id))
    return recovered


async def wake_due_timers(queue: JobQueue) -> int:
    now = utcnow()
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(DurableTimer, Execution.status)
                .join(Execution, Execution.id == DurableTimer.execution_id)
                .where(
                    DurableTimer.fired_at.is_(None),
                    DurableTimer.wake_at <= now,
                    Execution.status == ExecutionStatus.waiting_for_timer,
                )
                .with_for_update(of=DurableTimer, skip_locked=True)
                .limit(100)
            )
        ).all()
        ids = [r[0].execution_id for r in rows]
        for timer, _ in rows:
            timer.fired_at = now
    for execution_id in ids:
        await queue.enqueue(Job.resume_execution, str(execution_id), job_id=resume_job_id(execution_id))
    return len(ids)


async def expire_approvals(queue: JobQueue) -> int:
    now = utcnow()
    async with session_scope() as session:
        rows = list(
            (
                await session.scalars(
                    select(Approval)
                    .where(Approval.status == ApprovalStatus.pending, Approval.expires_at < now)
                    .with_for_update(skip_locked=True)
                    .limit(100)
                )
            ).all()
        )
        executions: set[uuid.UUID] = set()
        for approval in rows:
            approval.status = ApprovalStatus.expired
            approval.decided_at = now
            approval.reason = "Expired without a decision"
            if approval.tool_call_id:
                await session.execute(
                    sa.update(ToolCall)
                    .where(ToolCall.id == approval.tool_call_id)
                    .values(status=ToolCallStatus.rejected)
                )
            executions.add(approval.execution_id)
        for execution_id in executions:
            await session.execute(
                sa.update(Execution)
                .where(Execution.id == execution_id, Execution.status == ExecutionStatus.paused_for_review)
                .values(status=ExecutionStatus.resuming)
            )
    for execution_id in executions:
        await queue.enqueue(Job.resume_execution, str(execution_id), job_id=resume_job_id(execution_id))
    return len(rows)
