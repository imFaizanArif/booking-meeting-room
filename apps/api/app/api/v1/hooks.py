"""Inbound webhook triggers, authenticated by an HMAC signature per pipeline."""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB, Auth, client_ip, rate_limit
from app.core.enums import Role, TriggerKind
from app.core.errors import NotFound, Unauthenticated, ValidationFailed
from app.core.security import new_token, verify_signature
from app.models import Pipeline, PipelineVersion
from app.ratelimit.limiter import Limit
from app.schemas.runtime import ExecutionOut
from app.secrets.manager import get_secret_manager
from app.services import secret_fields
from app.services.context import Actor
from app.services.dashboard import execution_outs
from app.services.executions import create_execution

router = APIRouter(tags=["webhooks"])


class WebhookSecretOut(BaseModel):
    secret: str
    header: str = "X-Agent-Platform-Signature"
    format: str = "t=<unix>,v1=<hex hmac_sha256(secret, '<unix>.' + body)>"


@router.post("/pipelines/{pipeline_id}/webhook-secret", response_model=WebhookSecretOut)
async def rotate_webhook_secret(pipeline_id: uuid.UUID, ctx: Auth, session: DB) -> WebhookSecretOut:
    """Generate a new signing secret. It is shown once."""
    ctx.require(Role.owner)
    pipeline = await session.scalar(select(Pipeline).where(Pipeline.id == pipeline_id,
                                                           Pipeline.workspace_id == ctx.workspace_id))
    if pipeline is None:
        raise NotFound("Pipeline not found")
    secret = new_token()
    pipeline.webhook_secret_ref = await secret_fields.put_field(session, ctx, f"pipeline:{pipeline.id}:webhook",
                                                                secret)
    return WebhookSecretOut(secret=secret)


@router.post("/hooks/pipelines/{pipeline_id}", response_model=ExecutionOut, status_code=202)
async def webhook_trigger(pipeline_id: uuid.UUID, request: Request, session: DB,
                          x_agent_platform_signature: str = Header(default="")) -> ExecutionOut:
    await rate_limit(f"hook:{client_ip(request)}", Limit(60, 60))
    pipeline = await session.get(Pipeline, pipeline_id)
    if pipeline is None or pipeline.is_archived or not pipeline.webhook_secret_ref or not pipeline.latest_version_id:
        raise NotFound("Pipeline not found")
    body = await request.body()
    secret = await get_secret_manager().get(session, pipeline.workspace_id, pipeline.webhook_secret_ref)
    if not verify_signature(secret, body, x_agent_platform_signature):
        raise Unauthenticated("Invalid webhook signature")
    try:
        payload = json.loads(body or b"{}")
    except json.JSONDecodeError as exc:
        raise ValidationFailed("Body must be JSON") from exc
    if not isinstance(payload, dict):
        raise ValidationFailed("Body must be a JSON object")
    version = await session.get(PipelineVersion, pipeline.latest_version_id)
    assert version is not None
    execution = await create_execution(
        session, workspace_id=pipeline.workspace_id, pipeline=pipeline, version=version, input=payload,
        trigger=TriggerKind.webhook, actor=Actor("webhook", None, client_ip(request)), started_by_role=Role.operator)
    return (await execution_outs(session, [execution]))[0]
