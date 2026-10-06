"""Prompt studio: versioned templates, workspace variables and rendered previews."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit
from app.core.enums import AuditEventType, Role
from app.core.errors import Conflict, NotFound
from app.models import PromptTemplate, PromptTemplateVersion, PromptVariable
from app.prompts.render import preview, referenced_variables
from app.schemas.config import (
    PromptPreviewIn,
    PromptPreviewOut,
    PromptTemplateDetail,
    PromptTemplateIn,
    PromptTemplateOut,
    PromptVariableIn,
    PromptVariableOut,
    PromptVersionIn,
    PromptVersionOut,
)
from app.services.context import AuthContext

RUNTIME_NAMES = {"input", "nodes", "item", "index", "vars", "execution"}


async def _latest(session: AsyncSession, template: PromptTemplate) -> PromptTemplateVersion | None:
    return await session.scalar(select(PromptTemplateVersion).where(
        PromptTemplateVersion.template_id == template.id, PromptTemplateVersion.version == template.latest_version))


async def _out(session: AsyncSession, template: PromptTemplate) -> PromptTemplateOut:
    latest = await _latest(session, template)
    return PromptTemplateOut(id=template.id, name=template.name, description=template.description,
                             latest_version=template.latest_version, latest_body=latest.body if latest else "",
                             variables=list(latest.variables) if latest else [], updated_at=template.updated_at)


async def _get(session: AsyncSession, ctx: AuthContext, template_id: uuid.UUID) -> PromptTemplate:
    row = await session.scalar(select(PromptTemplate).where(PromptTemplate.id == template_id,
                                                            PromptTemplate.workspace_id == ctx.workspace_id))
    if row is None:
        raise NotFound("Prompt template not found")
    return row


async def list_templates(session: AsyncSession, ctx: AuthContext) -> list[PromptTemplateOut]:
    rows = (await session.scalars(select(PromptTemplate).where(PromptTemplate.workspace_id == ctx.workspace_id)
                                  .order_by(PromptTemplate.name))).all()
    return [await _out(session, r) for r in rows]


async def get_template(session: AsyncSession, ctx: AuthContext, template_id: uuid.UUID) -> PromptTemplateDetail:
    template = await _get(session, ctx, template_id)
    versions = (await session.scalars(select(PromptTemplateVersion).where(
        PromptTemplateVersion.template_id == template.id).order_by(PromptTemplateVersion.version.desc()))).all()
    base = await _out(session, template)
    return PromptTemplateDetail(**base.model_dump(),
                                versions=[PromptVersionOut.model_validate(v) for v in versions])


async def create_template(session: AsyncSession, ctx: AuthContext, data: PromptTemplateIn) -> PromptTemplateDetail:
    ctx.require(Role.operator)
    if await session.scalar(select(PromptTemplate.id).where(PromptTemplate.workspace_id == ctx.workspace_id,
                                                            PromptTemplate.name == data.name)):
        raise Conflict("A template with this name already exists")
    variables = sorted(referenced_variables(data.body))
    template = PromptTemplate(workspace_id=ctx.workspace_id, name=data.name, description=data.description,
                              latest_version=1)
    session.add(template)
    await session.flush()
    session.add(PromptTemplateVersion(template_id=template.id, version=1, body=data.body, variables=variables,
                                      created_by=ctx.user_id, change_note=data.change_note or "Initial version"))
    await audit(session, event_type=AuditEventType.config_created, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="prompt_template", entity_id=template.id, payload={"name": data.name, "version": 1})
    await session.flush()
    return await get_template(session, ctx, template.id)


async def add_version(session: AsyncSession, ctx: AuthContext, template_id: uuid.UUID,
                      data: PromptVersionIn) -> PromptTemplateDetail:
    ctx.require(Role.operator)
    template = await _get(session, ctx, template_id)
    version = template.latest_version + 1
    session.add(PromptTemplateVersion(template_id=template.id, version=version, body=data.body,
                                      variables=sorted(referenced_variables(data.body)), created_by=ctx.user_id,
                                      change_note=data.change_note))
    template.latest_version = version
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="prompt_template", entity_id=template.id, payload={"version": version,
                                                                              "note": data.change_note})
    await session.flush()
    return await get_template(session, ctx, template.id)


async def delete_template(session: AsyncSession, ctx: AuthContext, template_id: uuid.UUID) -> None:
    ctx.require(Role.operator)
    template = await _get(session, ctx, template_id)
    await session.delete(template)
    await audit(session, event_type=AuditEventType.config_deleted, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="prompt_template", entity_id=template_id, payload={"name": template.name})


async def preview_template(session: AsyncSession, ctx: AuthContext, data: PromptPreviewIn) -> PromptPreviewOut:
    variables = {v.key: v.value for v in (await session.scalars(
        select(PromptVariable).where(PromptVariable.workspace_id == ctx.workspace_id))).all()}
    context: dict[str, Any] = {**variables, "vars": variables, **data.sample}
    try:
        names = sorted(referenced_variables(data.body))
    except Exception:  # noqa: BLE001 - surfaced through `error`
        names = []
    rendered, unresolved, error = preview(data.body, context)
    return PromptPreviewOut(rendered=rendered, unresolved=unresolved, error=error, variables=names)


async def list_variables(session: AsyncSession, ctx: AuthContext) -> list[PromptVariableOut]:
    rows = (await session.scalars(select(PromptVariable).where(PromptVariable.workspace_id == ctx.workspace_id)
                                  .order_by(PromptVariable.key))).all()
    return [PromptVariableOut.model_validate(r) for r in rows]


async def upsert_variable(session: AsyncSession, ctx: AuthContext, data: PromptVariableIn) -> PromptVariableOut:
    ctx.require(Role.operator)
    row = await session.scalar(select(PromptVariable).where(PromptVariable.workspace_id == ctx.workspace_id,
                                                            PromptVariable.key == data.key))
    if row is None:
        row = PromptVariable(workspace_id=ctx.workspace_id, key=data.key, value=data.value,
                             description=data.description)
        session.add(row)
    else:
        row.value, row.description = data.value, data.description
    await audit(session, event_type=AuditEventType.config_updated, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="prompt_variable", entity_id=data.key, payload={"key": data.key, "length": len(data.value)})
    await session.flush()
    await session.refresh(row)
    return PromptVariableOut.model_validate(row)


async def delete_variable(session: AsyncSession, ctx: AuthContext, key: str) -> None:
    ctx.require(Role.operator)
    row = await session.scalar(select(PromptVariable).where(PromptVariable.workspace_id == ctx.workspace_id,
                                                            PromptVariable.key == key))
    if row is None:
        raise NotFound("Variable not found")
    await session.delete(row)
    await audit(session, event_type=AuditEventType.config_deleted, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="prompt_variable", entity_id=key)
