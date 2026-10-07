from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import DB, Auth
from app.core.enums import ExecutionStatus
from app.events.schemas import ExecutionEventOut
from app.schemas.common import Page
from app.schemas.pipeline_graph import PipelineGraph
from app.schemas.runtime import (
    ControlIn,
    ExecutionDetail,
    ExecutionNodeOut,
    ExecutionOut,
    LLMUsageOut,
    ToolCallOut,
)
from app.services import executions as service
from app.services.approvals import _enrich
from app.services.dashboard import execution_outs

router = APIRouter(prefix="/executions", tags=["executions"])


@router.get("", response_model=Page[ExecutionOut])
async def list_executions(ctx: Auth, session: DB, status: list[ExecutionStatus] | None = Query(default=None),
                          pipeline_id: uuid.UUID | None = None, limit: int = Query(50, le=200),
                          offset: int = 0) -> Page[ExecutionOut]:
    rows, total = await service.list_executions(session, ctx, status=status, pipeline_id=pipeline_id,
                                                limit=limit, offset=offset)
    return Page(items=await execution_outs(session, [r for r, _ in rows]), total=total, limit=limit, offset=offset)


@router.get("/{execution_id}", response_model=ExecutionDetail)
async def get_execution(execution_id: uuid.UUID, ctx: Auth, session: DB) -> ExecutionDetail:
    data = await service.execution_detail(session, ctx, execution_id)
    execution = data["execution"]
    snapshot = dict(execution.config_snapshot or {})
    return ExecutionDetail(
        execution=(await execution_outs(session, [execution]))[0],
        nodes=[ExecutionNodeOut.model_validate(n) for n in data["nodes"]],
        tool_calls=[ToolCallOut.model_validate(c) for c in data["tool_calls"]],
        usage=[LLMUsageOut.model_validate(u) for u in data["usage"]],
        approvals=await _enrich(session, data["approvals"]),
        graph=PipelineGraph.model_validate(snapshot.get("graph") or {}),
        snapshot=snapshot,
    )


@router.get("/{execution_id}/events", response_model=list[ExecutionEventOut])
async def list_execution_events(execution_id: uuid.UUID, ctx: Auth, session: DB, after_seq: int = 0,
                                limit: int = Query(500, le=2000)) -> list[ExecutionEventOut]:
    rows = await service.list_events(session, ctx, execution_id, after_seq, limit)
    return [ExecutionEventOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/{execution_id}/control", response_model=ExecutionOut)
async def control_execution(execution_id: uuid.UUID, data: ControlIn, ctx: Auth, session: DB) -> ExecutionOut:
    execution = await service.control(session, ctx, execution_id, data.action)
    return (await execution_outs(session, [execution]))[0]


@router.post("/{execution_id}/restart", response_model=ExecutionOut, status_code=202)
async def restart_execution(execution_id: uuid.UUID, ctx: Auth, session: DB) -> ExecutionOut:
    execution = await service.restart(session, ctx, execution_id)
    return (await execution_outs(session, [execution]))[0]


