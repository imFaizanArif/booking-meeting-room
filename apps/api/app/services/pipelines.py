"""Pipelines and their immutable versions."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit
from app.core.enums import AuditEventType, Role
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.ids import slugify
from app.mcp.types import namespaced
from app.models import Execution, MCPServer, MCPTool, Pipeline, PipelineVersion, Schedule
from app.orchestration.validation import parse_graph, validate_graph
from app.schemas.pipeline_graph import NODE_CONFIG_MODELS, PipelineGraph
from app.schemas.runtime import (
    GraphIssueOut,
    NodeTypeOut,
    PipelineDetail,
    PipelineIn,
    PipelineOut,
    PipelinePatch,
    PipelineVersionIn,
    PipelineVersionOut,
    PipelineVersionSummary,
    ValidationOut,
)
from app.services.context import AuthContext

NODE_DESCRIPTIONS = {
    "trigger": ("Trigger", "Start of the pipeline. Defines the input schema and allowed triggers."),
    "llm": ("LLM", "One model call with a rendered prompt. Optional structured output. No tools."),
    "agent": ("Agent", "Model + tool loop over an explicit allow-list, bounded by iterations, calls and tokens."),
    "mcp_tool": ("MCP tool", "Deterministic call to one tool with arguments mapped from upstream outputs."),
    "condition": ("Condition", "Routes to the true or false branch using a safe expression."),
    "transform": ("Transform", "Reshape data with an expression, JSONPath or an object template."),
    "human_approval": ("Human approval", "Pause for a person to review, edit or reject data."),
    "notification": ("Notification", "Send a message to configured channels."),
    "delay": ("Delay", "Wait for a duration or until a time. The worker is released while waiting."),
    "end": ("End", "Declares the pipeline output."),
}


def graph_hash(graph: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(graph, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def node_types() -> list[NodeTypeOut]:
    from app.schemas.pipeline_graph import MAPPABLE

    return [
        NodeTypeOut(
            type=t,
            label=NODE_DESCRIPTIONS[t.value][0],
            description=NODE_DESCRIPTIONS[t.value][1],
            config_schema=model.model_json_schema(),
            mappable=t in MAPPABLE,
        )
        for t, model in NODE_CONFIG_MODELS.items()
    ]


async def known_tools(session: AsyncSession, workspace_id: uuid.UUID) -> set[str]:
    rows = (
        await session.execute(
            select(MCPServer.slug, MCPTool.name)
            .join(MCPTool, MCPTool.server_id == MCPServer.id)
            .where(MCPServer.workspace_id == workspace_id, MCPTool.is_stale.is_(False))
        )
    ).all()
    return {namespaced(slug, name) for slug, name in rows}


async def validate(
    session: AsyncSession, ctx: AuthContext, raw: dict[str, Any]
) -> tuple[PipelineGraph | None, ValidationOut]:
    graph, parsed = parse_graph(raw)
    if graph is None:
        return None, ValidationOut(ok=False, issues=[GraphIssueOut(**i.__dict__) for i in parsed.issues])
    result = validate_graph(graph, known_tools=await known_tools(session, ctx.workspace_id))
    return graph, ValidationOut(ok=result.ok, issues=[GraphIssueOut(**i.__dict__) for i in result.issues])


async def _get(session: AsyncSession, ctx: AuthContext, pipeline_id: uuid.UUID) -> Pipeline:
    row = await session.scalar(
        select(Pipeline).where(Pipeline.id == pipeline_id, Pipeline.workspace_id == ctx.workspace_id)
    )
    if row is None:
        raise NotFound("Pipeline not found")
    return row


async def _out(session: AsyncSession, p: Pipeline) -> PipelineOut:
    out = PipelineOut.model_validate(p)
    if p.latest_version_id:
        version = await session.get(PipelineVersion, p.latest_version_id)
        out.node_count = len((version.graph or {}).get("nodes", [])) if version else 0
    last = (
        await session.execute(
            select(Execution.status, Execution.created_at)
            .where(Execution.pipeline_id == p.id)
            .order_by(Execution.created_at.desc())
            .limit(1)
        )
    ).first()
    if last:
        out.last_execution_status, out.last_execution_at = last[0], last[1]
    out.schedule_count = (
        await session.scalar(select(func.count()).select_from(Schedule).where(Schedule.pipeline_id == p.id)) or 0
    )
    return out


async def list_pipelines(session: AsyncSession, ctx: AuthContext, include_archived: bool = False) -> list[PipelineOut]:
    query = select(Pipeline).where(Pipeline.workspace_id == ctx.workspace_id)
    if not include_archived:
        query = query.where(Pipeline.is_archived.is_(False))
    rows = (await session.scalars(query.order_by(Pipeline.updated_at.desc()))).all()
    return [await _out(session, p) for p in rows]


async def get_pipeline(session: AsyncSession, ctx: AuthContext, pipeline_id: uuid.UUID) -> PipelineDetail:
    pipeline = await _get(session, ctx, pipeline_id)
    versions = (
        await session.scalars(
            select(PipelineVersion)
            .where(PipelineVersion.pipeline_id == pipeline.id)
            .order_by(PipelineVersion.version.desc())
        )
    ).all()
    latest = next((v for v in versions if v.id == pipeline.latest_version_id), None)
    base = await _out(session, pipeline)
    return PipelineDetail(
        **base.model_dump(),
        latest=PipelineVersionOut.model_validate(latest) if latest else None,
        versions=[PipelineVersionSummary.model_validate(v) for v in versions],
    )


async def get_version(
    session: AsyncSession, ctx: AuthContext, pipeline_id: uuid.UUID, version: int
) -> PipelineVersionOut:
    await _get(session, ctx, pipeline_id)
    row = await session.scalar(
        select(PipelineVersion).where(PipelineVersion.pipeline_id == pipeline_id, PipelineVersion.version == version)
    )
    if row is None:
        raise NotFound("Version not found")
    return PipelineVersionOut.model_validate(row)


async def _add_version(
    session: AsyncSession, ctx: AuthContext, pipeline: Pipeline, raw: dict[str, Any], note: str | None
) -> PipelineVersion:
    graph, result = await validate(session, ctx, raw)
    if graph is None or not result.ok:
        raise ValidationFailed(
            "The pipeline has errors. Fix them before saving.",
            details={"issues": [i.model_dump() for i in result.issues]},
        )
    canonical = graph.model_dump(mode="json")
    digest = graph_hash(canonical)
    if pipeline.latest_version_id:
        current = await session.get(PipelineVersion, pipeline.latest_version_id)
        if current is not None and current.graph_hash == digest:
            return current  # no change, no new version
    version = PipelineVersion(
        pipeline_id=pipeline.id,
        version=pipeline.latest_version_number + 1,
        graph=canonical,
        graph_hash=digest,
        change_note=note,
        created_by=ctx.user_id,
    )
    session.add(version)
    await session.flush()
    pipeline.latest_version_id = version.id
    pipeline.latest_version_number = version.version
    await audit(
        session,
        event_type=AuditEventType.config_updated,
        actor=ctx,
        workspace_id=ctx.workspace_id,
        entity_type="pipeline",
        entity_id=pipeline.id,
        payload={"version": version.version, "hash": digest[:12], "note": note},
    )
    return version


def starter_graph() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "trigger", "type": "trigger", "name": "Trigger", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "end", "type": "end", "name": "End", "position": {"x": 320, "y": 0}, "config": {"output": "=input"}},
        ],
        "edges": [{"id": "e_trigger_end", "source": "trigger", "target": "end"}],
    }


async def create_pipeline(session: AsyncSession, ctx: AuthContext, data: PipelineIn) -> PipelineDetail:
    ctx.require(Role.operator)
    slug = slugify(data.name)[:100]
    if await session.scalar(
        select(Pipeline.id).where(Pipeline.workspace_id == ctx.workspace_id, Pipeline.slug == slug)
    ):
        raise Conflict("A pipeline with this name already exists")
    pipeline = Pipeline(workspace_id=ctx.workspace_id, name=data.name, slug=slug, description=data.description)
    session.add(pipeline)
    await session.flush()
    await audit(
        session,
        event_type=AuditEventType.config_created,
        actor=ctx,
        workspace_id=ctx.workspace_id,
        entity_type="pipeline",
        entity_id=pipeline.id,
        payload={"name": data.name},
    )
    raw = data.graph.model_dump(mode="json") if data.graph else starter_graph()
    await _add_version(session, ctx, pipeline, raw, "Created")
    await session.flush()
    return await get_pipeline(session, ctx, pipeline.id)


async def save_version(
    session: AsyncSession, ctx: AuthContext, pipeline_id: uuid.UUID, data: PipelineVersionIn
) -> PipelineDetail:
    ctx.require(Role.operator)
    pipeline = await _get(session, ctx, pipeline_id)
    await _add_version(session, ctx, pipeline, data.graph, data.change_note)
    await session.flush()
    return await get_pipeline(session, ctx, pipeline.id)


async def update_pipeline(
    session: AsyncSession, ctx: AuthContext, pipeline_id: uuid.UUID, data: PipelinePatch
) -> PipelineDetail:
    ctx.require(Role.operator)
    pipeline = await _get(session, ctx, pipeline_id)
    changes = data.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(pipeline, key, value)
    await audit(
        session,
        event_type=AuditEventType.config_updated,
        actor=ctx,
        workspace_id=ctx.workspace_id,
        entity_type="pipeline",
        entity_id=pipeline.id,
        payload={"changes": changes},
    )
    await session.flush()
    return await get_pipeline(session, ctx, pipeline.id)


async def delete_pipeline(session: AsyncSession, ctx: AuthContext, pipeline_id: uuid.UUID) -> None:
    ctx.require(Role.owner)
    pipeline = await _get(session, ctx, pipeline_id)
    has_runs = await session.scalar(
        select(func.count()).select_from(Execution).where(Execution.pipeline_id == pipeline.id)
    )
    if has_runs:
        pipeline.is_archived = True  # keep history reproducible
    else:
        await session.delete(pipeline)
    await audit(
        session,
        event_type=AuditEventType.config_deleted,
        actor=ctx,
        workspace_id=ctx.workspace_id,
        entity_type="pipeline",
        entity_id=pipeline_id,
        payload={"name": pipeline.name, "archived_instead": bool(has_runs)},
    )
