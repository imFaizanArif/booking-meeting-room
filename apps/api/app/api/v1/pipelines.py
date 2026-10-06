from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter

from app.api.deps import DB, Auth
from app.schemas.common import Ok
from app.schemas.runtime import (
    ExecutionOut,
    NodeTypeOut,
    PipelineDetail,
    PipelineIn,
    PipelineOut,
    PipelinePatch,
    PipelineVersionIn,
    PipelineVersionOut,
    RunIn,
    ValidationOut,
)
from app.services import executions as executions_service
from app.services import pipelines as service
from app.services.dashboard import execution_outs

router = APIRouter(tags=["pipelines"])


@router.get("/node-types", response_model=list[NodeTypeOut])
async def list_node_types(ctx: Auth) -> list[NodeTypeOut]:
    return service.node_types()


@router.get("/pipelines", response_model=list[PipelineOut])
async def list_pipelines(ctx: Auth, session: DB, include_archived: bool = False) -> list[PipelineOut]:
    return await service.list_pipelines(session, ctx, include_archived)


@router.post("/pipelines", response_model=PipelineDetail, status_code=201)
async def create_pipeline(data: PipelineIn, ctx: Auth, session: DB) -> PipelineDetail:
    return await service.create_pipeline(session, ctx, data)


@router.post("/pipelines/validate", response_model=ValidationOut)
async def validate_pipeline(graph: dict[str, Any], ctx: Auth, session: DB) -> ValidationOut:
    return (await service.validate(session, ctx, graph))[1]


@router.get("/pipelines/{pipeline_id}", response_model=PipelineDetail)
async def get_pipeline(pipeline_id: uuid.UUID, ctx: Auth, session: DB) -> PipelineDetail:
    return await service.get_pipeline(session, ctx, pipeline_id)


@router.patch("/pipelines/{pipeline_id}", response_model=PipelineDetail)
async def update_pipeline(pipeline_id: uuid.UUID, data: PipelinePatch, ctx: Auth, session: DB) -> PipelineDetail:
    return await service.update_pipeline(session, ctx, pipeline_id, data)


@router.delete("/pipelines/{pipeline_id}", response_model=Ok)
async def delete_pipeline(pipeline_id: uuid.UUID, ctx: Auth, session: DB) -> Ok:
    await service.delete_pipeline(session, ctx, pipeline_id)
    return Ok()


@router.post("/pipelines/{pipeline_id}/versions", response_model=PipelineDetail, status_code=201)
async def save_pipeline_version(pipeline_id: uuid.UUID, data: PipelineVersionIn, ctx: Auth,
                                session: DB) -> PipelineDetail:
    return await service.save_version(session, ctx, pipeline_id, data)


@router.get("/pipelines/{pipeline_id}/versions/{version}", response_model=PipelineVersionOut)
async def get_pipeline_version(pipeline_id: uuid.UUID, version: int, ctx: Auth, session: DB) -> PipelineVersionOut:
    return await service.get_version(session, ctx, pipeline_id, version)


@router.post("/pipelines/{pipeline_id}/run", response_model=ExecutionOut, status_code=202)
async def run_pipeline(pipeline_id: uuid.UUID, data: RunIn, ctx: Auth, session: DB) -> ExecutionOut:
    execution = await executions_service.start_manual(session, ctx, pipeline_id, data.input, data.version)
    return (await execution_outs(session, [execution]))[0]
