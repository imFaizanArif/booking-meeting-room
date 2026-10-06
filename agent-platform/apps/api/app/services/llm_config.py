"""LLM providers and models: CRUD, defaults, connection tests (run in the worker)."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit, diff
from app.core.enums import AuditEventType, Role
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.redaction import redactor
from app.core.ssrf import guard_url
from app.core.time import utcnow
from app.llm.registry import KEYLESS
from app.models import LLMModel, LLMProvider
from app.schemas.config import ModelIn, ModelOut, ModelPatch, ProviderIn, ProviderOut, ProviderPatch, TestResult
from app.services import secret_fields
from app.services.context import AuthContext
from app.workers.queue import Job, get_queue


def _snapshot(p: LLMProvider) -> dict[str, Any]:
    return {"name": p.name, "base_url": p.base_url, "is_active": p.is_active, "rpm": p.requests_per_minute,
            "max_concurrency": p.max_concurrency, "api_key_set": bool(p.api_key_secret_ref)}


async def provider_out(session: AsyncSession, p: LLMProvider) -> ProviderOut:
    count = await session.scalar(select(func.count()).select_from(LLMModel).where(LLMModel.provider_id == p.id)) or 0
    return ProviderOut(
        id=p.id, name=p.name, provider_type=p.provider_type, base_url=p.base_url,
        api_key=await secret_fields.state(session, p.workspace_id, p.api_key_secret_ref), is_active=p.is_active,
        metadata=p.metadata_ or {}, requests_per_minute=p.requests_per_minute, max_concurrency=p.max_concurrency,
        last_test_ok=p.last_test_ok, last_test_at=p.last_test_at, last_test_message=p.last_test_message,
        model_count=count, created_at=p.created_at, updated_at=p.updated_at,
    )


async def _get_provider(session: AsyncSession, ctx: AuthContext, provider_id: uuid.UUID) -> LLMProvider:
    row = await session.scalar(select(LLMProvider).where(LLMProvider.id == provider_id,
                                                         LLMProvider.workspace_id == ctx.workspace_id))
    if row is None:
        raise NotFound("Provider not found")
    return row


async def list_providers(session: AsyncSession, ctx: AuthContext) -> list[ProviderOut]:
    rows = (await session.scalars(select(LLMProvider).where(LLMProvider.workspace_id == ctx.workspace_id)
                                  .order_by(LLMProvider.name))).all()
    return [await provider_out(session, r) for r in rows]


async def create_provider(session: AsyncSession, ctx: AuthContext, data: ProviderIn) -> ProviderOut:
    ctx.require(Role.owner)
    if data.base_url:
        await guard_url(data.base_url)
    exists = await session.scalar(select(LLMProvider.id).where(LLMProvider.workspace_id == ctx.workspace_id,
                                                               LLMProvider.name == data.name))
    if exists:
        raise Conflict("A provider with this name already exists")
    if data.is_active and not data.api_key and data.provider_type not in KEYLESS:
        raise ValidationFailed("Add an API key before activating this provider",
                               details={"fields": [{"field": "api_key", "message": "Required to activate"}]})
    provider = LLMProvider(workspace_id=ctx.workspace_id, name=data.name, provider_type=data.provider_type,
                           base_url=data.base_url, is_active=data.is_active, metadata_=data.metadata,
                           requests_per_minute=data.requests_per_minute, max_concurrency=data.max_concurrency)
    session.add(provider)
    await session.flush()
    if data.api_key:
        provider.api_key_secret_ref = await secret_fields.put_field(session, ctx, f"provider:{provider.id}:api_key",
                                                                    data.api_key)
    await audit(session, event_type=AuditEventType.config_created, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="llm_provider", entity_id=provider.id, payload=_snapshot(provider))
    return await provider_out(session, provider)


async def update_provider(session: AsyncSession, ctx: AuthContext, provider_id: uuid.UUID,
                          data: ProviderPatch) -> ProviderOut:
    ctx.require(Role.owner)
    provider = await _get_provider(session, ctx, provider_id)
    before = _snapshot(provider)
    patch = data.model_dump(exclude_unset=True, exclude={"api_key", "clear_api_key", "metadata"})
    if patch.get("base_url"):
        await guard_url(patch["base_url"])
    for key, value in patch.items():
        setattr(provider, key, value)
    if data.metadata is not None:
        provider.metadata_ = data.metadata
    if data.clear_api_key:
        await secret_fields.delete_field(session, ctx, provider.api_key_secret_ref)
        provider.api_key_secret_ref = None
    if data.api_key:
        provider.api_key_secret_ref = await secret_fields.put_field(session, ctx, f"provider:{provider.id}:api_key",
                                                                    data.api_key)
    if provider.is_active and not provider.api_key_secret_ref and provider.provider_type not in KEYLESS:
        raise ValidationFailed("Add an API key before activating this provider",
                               details={"fields": [{"field": "api_key", "message": "Required to activate"}]})
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="llm_provider", entity_id=provider.id, payload={"changes": diff(before, _snapshot(provider))})
    await session.flush()
    return await provider_out(session, provider)


async def delete_provider(session: AsyncSession, ctx: AuthContext, provider_id: uuid.UUID) -> None:
    ctx.require(Role.owner)
    provider = await _get_provider(session, ctx, provider_id)
    await secret_fields.delete_field(session, ctx, provider.api_key_secret_ref)
    await session.delete(provider)
    await audit(session, event_type=AuditEventType.config_deleted, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="llm_provider", entity_id=provider_id, payload={"name": provider.name})


async def test_provider(session: AsyncSession, ctx: AuthContext, provider_id: uuid.UUID) -> TestResult:
    ctx.require(Role.operator)
    provider = await _get_provider(session, ctx, provider_id)
    await session.commit()
    try:
        result: dict[str, Any] = await get_queue().call(Job.test_provider, str(provider.id), timeout_s=40)
    except TimeoutError:
        result = {"ok": False, "message": "No worker answered within 40s. Is the worker running?"}
    message = redactor.redact_text(str(result.get("message", "")))[:500]
    await session.execute(sa.update(LLMProvider).where(LLMProvider.id == provider.id).values(
        last_test_ok=bool(result.get("ok")), last_test_at=utcnow(), last_test_message=message))
    return TestResult(ok=bool(result.get("ok")), message=message)


# ---- models ---------------------------------------------------------------------------------------


async def model_out(session: AsyncSession, m: LLMModel) -> ModelOut:
    provider = await session.get(LLMProvider, m.provider_id)
    out = ModelOut.model_validate(m)
    out.provider_name = provider.name if provider else ""
    out.provider_type = provider.provider_type if provider else None
    return out


async def list_models(session: AsyncSession, ctx: AuthContext) -> list[ModelOut]:
    rows = (await session.scalars(select(LLMModel).where(LLMModel.workspace_id == ctx.workspace_id)
                                  .order_by(LLMModel.display_name))).all()
    return [await model_out(session, m) for m in rows]


async def _get_model(session: AsyncSession, ctx: AuthContext, model_id: uuid.UUID) -> LLMModel:
    row = await session.scalar(select(LLMModel).where(LLMModel.id == model_id,
                                                      LLMModel.workspace_id == ctx.workspace_id))
    if row is None:
        raise NotFound("Model not found")
    return row


async def create_model(session: AsyncSession, ctx: AuthContext, data: ModelIn) -> ModelOut:
    ctx.require(Role.owner)
    await _get_provider(session, ctx, data.provider_id)
    model = LLMModel(workspace_id=ctx.workspace_id, **data.model_dump())
    session.add(model)
    try:
        await session.flush()
    except sa.exc.IntegrityError as exc:
        raise Conflict("This provider already has a model with that name") from exc
    await audit(session, event_type=AuditEventType.config_created, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="llm_model", entity_id=model.id, payload=data.model_dump(mode="json"))
    return await model_out(session, model)


async def update_model(session: AsyncSession, ctx: AuthContext, model_id: uuid.UUID, data: ModelPatch) -> ModelOut:
    ctx.require(Role.owner)
    model = await _get_model(session, ctx, model_id)
    changes = data.model_dump(exclude_unset=True)
    before = {k: getattr(model, k) for k in changes}
    for key, value in changes.items():
        setattr(model, key, value)
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="llm_model", entity_id=model.id,
                payload={"changes": diff({k: str(v) for k, v in before.items()}, {k: str(v) for k, v in changes.items()})})
    await session.flush()
    return await model_out(session, model)


async def set_default_model(session: AsyncSession, ctx: AuthContext, model_id: uuid.UUID) -> ModelOut:
    ctx.require(Role.owner)
    model = await _get_model(session, ctx, model_id)
    await session.execute(sa.update(LLMModel).where(LLMModel.workspace_id == ctx.workspace_id)
                          .values(is_default=False))
    model.is_default = True
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="llm_model", entity_id=model.id, payload={"is_default": True})
    await session.flush()
    return await model_out(session, model)


async def delete_model(session: AsyncSession, ctx: AuthContext, model_id: uuid.UUID) -> None:
    ctx.require(Role.owner)
    model = await _get_model(session, ctx, model_id)
    await session.delete(model)
    await audit(session, event_type=AuditEventType.config_deleted, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="llm_model", entity_id=model_id, payload={"model": model.model_name})
