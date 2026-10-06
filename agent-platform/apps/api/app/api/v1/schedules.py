from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import DB, Auth
from app.schemas.common import Ok
from app.schemas.runtime import ScheduleFireOut, ScheduleIn, ScheduleOut
from app.services import schedules as service

router = APIRouter(prefix="/schedules", tags=["schedules"])


@router.get("", response_model=list[ScheduleOut])
async def list_schedules(ctx: Auth, session: DB) -> list[ScheduleOut]:
    return await service.list_schedules(session, ctx)


@router.post("", response_model=ScheduleOut, status_code=201)
async def create_schedule(data: ScheduleIn, ctx: Auth, session: DB) -> ScheduleOut:
    return await service.create_schedule(session, ctx, data)


@router.put("/{schedule_id}", response_model=ScheduleOut)
async def update_schedule(schedule_id: uuid.UUID, data: ScheduleIn, ctx: Auth, session: DB) -> ScheduleOut:
    return await service.update_schedule(session, ctx, schedule_id, data)


@router.delete("/{schedule_id}", response_model=Ok)
async def delete_schedule(schedule_id: uuid.UUID, ctx: Auth, session: DB) -> Ok:
    await service.delete_schedule(session, ctx, schedule_id)
    return Ok()


@router.get("/{schedule_id}/fires", response_model=list[ScheduleFireOut])
async def list_schedule_fires(schedule_id: uuid.UUID, ctx: Auth, session: DB) -> list[ScheduleFireOut]:
    return await service.list_fires(session, ctx, schedule_id)
