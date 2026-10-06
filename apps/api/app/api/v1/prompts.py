from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import DB, Auth
from app.schemas.common import Ok
from app.schemas.config import (
    PromptPreviewIn,
    PromptPreviewOut,
    PromptTemplateDetail,
    PromptTemplateIn,
    PromptTemplateOut,
    PromptVariableIn,
    PromptVariableOut,
    PromptVersionIn,
)
from app.services import prompts as service

router = APIRouter(tags=["prompts"])


@router.get("/prompts", response_model=list[PromptTemplateOut])
async def list_prompts(ctx: Auth, session: DB) -> list[PromptTemplateOut]:
    return await service.list_templates(session, ctx)


@router.post("/prompts", response_model=PromptTemplateDetail, status_code=201)
async def create_prompt(data: PromptTemplateIn, ctx: Auth, session: DB) -> PromptTemplateDetail:
    return await service.create_template(session, ctx, data)


@router.get("/prompts/{template_id}", response_model=PromptTemplateDetail)
async def get_prompt(template_id: uuid.UUID, ctx: Auth, session: DB) -> PromptTemplateDetail:
    return await service.get_template(session, ctx, template_id)


@router.post("/prompts/{template_id}/versions", response_model=PromptTemplateDetail, status_code=201)
async def add_prompt_version(template_id: uuid.UUID, data: PromptVersionIn, ctx: Auth,
                             session: DB) -> PromptTemplateDetail:
    return await service.add_version(session, ctx, template_id, data)


@router.delete("/prompts/{template_id}", response_model=Ok)
async def delete_prompt(template_id: uuid.UUID, ctx: Auth, session: DB) -> Ok:
    await service.delete_template(session, ctx, template_id)
    return Ok()


@router.post("/prompts/preview", response_model=PromptPreviewOut)
async def preview_prompt(data: PromptPreviewIn, ctx: Auth, session: DB) -> PromptPreviewOut:
    return await service.preview_template(session, ctx, data)


@router.get("/prompt-variables", response_model=list[PromptVariableOut])
async def list_prompt_variables(ctx: Auth, session: DB) -> list[PromptVariableOut]:
    return await service.list_variables(session, ctx)


@router.put("/prompt-variables", response_model=PromptVariableOut)
async def upsert_prompt_variable(data: PromptVariableIn, ctx: Auth, session: DB) -> PromptVariableOut:
    return await service.upsert_variable(session, ctx, data)


@router.delete("/prompt-variables/{key}", response_model=Ok)
async def delete_prompt_variable(key: str, ctx: Auth, session: DB) -> Ok:
    await service.delete_variable(session, ctx, key)
    return Ok()
