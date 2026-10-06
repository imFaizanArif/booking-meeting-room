"""Schedules: CRUD and fire history. The scheduler process does the firing."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit
from app.core.enums import AuditEventType, Role
from app.core.errors import NotFound
from app.core.time import utcnow
from app.models import Pipeline, Schedule, ScheduleFire
from app.scheduler.timing import next_fire, validate_schedule
from app.schemas.runtime import ScheduleFireOut, ScheduleIn, ScheduleOut
from app.services.context import AuthContext


async def _out(session: AsyncSession, s: Schedule) -> ScheduleOut:
    out = ScheduleOut.model_validate(s)
    pipeline = await session.get(Pipeline, s.pipeline_id)
    out.pipeline_name = pipeline.name if pipeline else ""
    return out


async def _get(session: AsyncSession, ctx: AuthContext, schedule_id: uuid.UUID) -> Schedule:
    row = await session.scalar(select(Schedule).where(Schedule.id == schedule_id,
                                                      Schedule.workspace_id == ctx.workspace_id))
    if row is None:
        raise NotFound("Schedule not found")
    return row


def _apply(row: Schedule, data: ScheduleIn) -> None:
    validate_schedule(data.kind, cron=data.cron, interval_seconds=data.interval_seconds,
                      daily_time=data.daily_time, timezone=data.timezone)
    for key, value in data.model_dump().items():
        setattr(row, key, value)
    row.next_run_at = next_fire(data.kind, after=utcnow(), cron=data.cron, interval_seconds=data.interval_seconds,
                                daily_time=data.daily_time, timezone=data.timezone) if data.is_active else None


async def list_schedules(session: AsyncSession, ctx: AuthContext) -> list[ScheduleOut]:
    rows = (await session.scalars(select(Schedule).where(Schedule.workspace_id == ctx.workspace_id)
                                  .order_by(Schedule.next_run_at.nulls_last()))).all()
    return [await _out(session, r) for r in rows]


async def create_schedule(session: AsyncSession, ctx: AuthContext, data: ScheduleIn) -> ScheduleOut:
    ctx.require(Role.operator)
    if await session.scalar(select(Pipeline.id).where(Pipeline.id == data.pipeline_id,
                                                      Pipeline.workspace_id == ctx.workspace_id)) is None:
        raise NotFound("Pipeline not found")
    row = Schedule(workspace_id=ctx.workspace_id)
    _apply(row, data)
    session.add(row)
    await session.flush()
    await audit(session, event_type=AuditEventType.config_created, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="schedule", entity_id=row.id, payload=data.model_dump(mode="json"))
    return await _out(session, row)


async def update_schedule(session: AsyncSession, ctx: AuthContext, schedule_id: uuid.UUID,
                          data: ScheduleIn) -> ScheduleOut:
    ctx.require(Role.operator)
    row = await _get(session, ctx, schedule_id)
    _apply(row, data)
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="schedule", entity_id=row.id, payload=data.model_dump(mode="json"))
    await session.flush()
    return await _out(session, row)


async def delete_schedule(session: AsyncSession, ctx: AuthContext, schedule_id: uuid.UUID) -> None:
    ctx.require(Role.operator)
    row = await _get(session, ctx, schedule_id)
    await session.delete(row)
    await audit(session, event_type=AuditEventType.config_deleted, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="schedule", entity_id=schedule_id, payload={"name": row.name})


async def list_fires(session: AsyncSession, ctx: AuthContext, schedule_id: uuid.UUID,
                     limit: int = 50) -> list[ScheduleFireOut]:
    await _get(session, ctx, schedule_id)
    rows = (await session.scalars(select(ScheduleFire).where(ScheduleFire.schedule_id == schedule_id)
                                  .order_by(ScheduleFire.fire_at.desc()).limit(limit))).all()
    return [ScheduleFireOut.model_validate(r) for r in rows]
