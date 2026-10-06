from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import DB, Auth
from app.schemas.common import Ok
from app.schemas.config import ModelIn, ModelOut, ModelPatch, ProviderIn, ProviderOut, ProviderPatch, TestResult
from app.services import llm_config as service

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(ctx: Auth, session: DB) -> list[ProviderOut]:
    return await service.list_providers(session, ctx)


@router.post("/providers", response_model=ProviderOut, status_code=201)
async def create_provider(data: ProviderIn, ctx: Auth, session: DB) -> ProviderOut:
    return await service.create_provider(session, ctx, data)


@router.patch("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider(provider_id: uuid.UUID, data: ProviderPatch, ctx: Auth, session: DB) -> ProviderOut:
    return await service.update_provider(session, ctx, provider_id, data)


@router.delete("/providers/{provider_id}", response_model=Ok)
async def delete_provider(provider_id: uuid.UUID, ctx: Auth, session: DB) -> Ok:
    await service.delete_provider(session, ctx, provider_id)
    return Ok()


@router.post("/providers/{provider_id}/test", response_model=TestResult)
async def test_provider(provider_id: uuid.UUID, ctx: Auth, session: DB) -> TestResult:
    return await service.test_provider(session, ctx, provider_id)


@router.get("/models", response_model=list[ModelOut])
async def list_models(ctx: Auth, session: DB) -> list[ModelOut]:
    return await service.list_models(session, ctx)


@router.post("/models", response_model=ModelOut, status_code=201)
async def create_model(data: ModelIn, ctx: Auth, session: DB) -> ModelOut:
    return await service.create_model(session, ctx, data)


@router.patch("/models/{model_id}", response_model=ModelOut)
async def update_model(model_id: uuid.UUID, data: ModelPatch, ctx: Auth, session: DB) -> ModelOut:
    return await service.update_model(session, ctx, model_id, data)


@router.post("/models/{model_id}/default", response_model=ModelOut)
async def set_default_model(model_id: uuid.UUID, ctx: Auth, session: DB) -> ModelOut:
    return await service.set_default_model(session, ctx, model_id)


@router.delete("/models/{model_id}", response_model=Ok)
async def delete_model(model_id: uuid.UUID, ctx: Auth, session: DB) -> Ok:
    await service.delete_model(session, ctx, model_id)
    return Ok()
