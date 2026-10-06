"""Execution config snapshot: everything a run needs, frozen at start.

Running and historical executions read only from the snapshot, so config edits affect new
executions only. The snapshot holds secret *refs* (never values) and template bodies.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import NodeType, ProviderType, RiskLevel, Role
from app.core.errors import ValidationFailed
from app.core.time import utcnow
from app.mcp.types import namespaced
from app.models import (
    LLMModel,
    LLMProvider,
    MCPServer,
    MCPTool,
    Pipeline,
    PipelineVersion,
    PromptTemplate,
    PromptTemplateVersion,
    PromptVariable,
)
from app.schemas.pipeline_graph import AgentNode, LLMNode, PipelineGraph


class SnapshotLLM(BaseModel):
    provider_id: uuid.UUID
    provider_type: ProviderType
    provider_name: str
    base_url: str | None = None
    api_key_secret_ref: str | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    requests_per_minute: int | None = None
    max_concurrency: int | None = None
    model_id: uuid.UUID
    model_name: str
    context_window: int
    supports_tools: bool
    supports_json_schema: bool
    input_price_per_mtok: Decimal
    output_price_per_mtok: Decimal
    temperature: float | None = None
    max_tokens: int | None = None
    extras: dict[str, Any] = Field(default_factory=dict)


class SnapshotPrompt(BaseModel):
    template_id: uuid.UUID
    name: str
    version: int
    body: str


class SnapshotTool(BaseModel):
    tool_id: uuid.UUID
    server_id: uuid.UUID
    server_slug: str
    name: str
    namespaced_name: str
    description: str = ""
    input_schema: dict[str, Any]
    schema_hash: str
    is_enabled: bool
    is_read_only: bool
    is_destructive: bool
    requires_approval: bool
    risk_level: RiskLevel


class SnapshotServer(BaseModel):
    server_id: uuid.UUID
    slug: str
    name: str


class SnapshotPolicy(BaseModel):
    started_by_role: Role | None = None
    retry_budget: int = 20
    approval_expiry_minutes: int | None = None


class ConfigSnapshot(BaseModel):
    pipeline_id: uuid.UUID
    pipeline_name: str
    pipeline_version_id: uuid.UUID
    pipeline_version: int
    graph_hash: str
    graph: PipelineGraph
    llm: dict[str, SnapshotLLM] = Field(default_factory=dict, description="node_id -> resolved model")
    prompts: dict[str, SnapshotPrompt] = Field(default_factory=dict, description="node_id -> system prompt")
    variables: dict[str, str] = Field(default_factory=dict)
    tools: dict[str, SnapshotTool] = Field(default_factory=dict, description="namespaced name -> tool")
    servers: dict[str, SnapshotServer] = Field(default_factory=dict)
    policy: SnapshotPolicy = Field(default_factory=SnapshotPolicy)
    created_at: datetime


async def _resolve_model(
    session: AsyncSession, workspace_id: uuid.UUID, node: LLMNode | AgentNode
) -> SnapshotLLM:
    cfg = node.config
    if cfg.model_id is not None:
        model = await session.scalar(
            select(LLMModel).where(LLMModel.id == cfg.model_id, LLMModel.workspace_id == workspace_id)
        )
    else:
        model = await session.scalar(
            select(LLMModel).where(LLMModel.workspace_id == workspace_id, LLMModel.is_default.is_(True))
        )
    if model is None:
        raise ValidationFailed(f"Node {node.id}: no model selected and no workspace default model",
                               details={"node_id": node.id})
    provider = await session.get(LLMProvider, model.provider_id)
    if provider is None or not provider.is_active or not model.is_active:
        raise ValidationFailed(
            f"Node {node.id}: model {model.display_name} or its provider is not active",
            details={"node_id": node.id, "model_id": str(model.id)},
        )
    defaults = dict(model.default_parameters or {})
    extras = {**(defaults.get("extras") or {})}
    for key, value in (cfg.provider_extras or {}).items():
        extras[key] = {**(extras.get(key) or {}), **value} if isinstance(value, dict) else value
    return SnapshotLLM(
        provider_id=provider.id, provider_type=provider.provider_type, provider_name=provider.name,
        base_url=provider.base_url, api_key_secret_ref=provider.api_key_secret_ref,
        provider_metadata=provider.metadata_ or {}, requests_per_minute=provider.requests_per_minute,
        max_concurrency=provider.max_concurrency, model_id=model.id, model_name=model.model_name,
        context_window=model.context_window, supports_tools=model.supports_tools,
        supports_json_schema=model.supports_json_schema,
        input_price_per_mtok=model.input_price_per_mtok, output_price_per_mtok=model.output_price_per_mtok,
        temperature=cfg.temperature if cfg.temperature is not None else defaults.get("temperature"),
        max_tokens=cfg.max_tokens if cfg.max_tokens is not None else defaults.get("max_tokens"),
        extras=extras,
    )


async def _resolve_prompt(
    session: AsyncSession, workspace_id: uuid.UUID, node: LLMNode | AgentNode
) -> SnapshotPrompt | None:
    ref = node.config.system_prompt
    if ref.template_id is None:
        if ref.inline:
            return SnapshotPrompt(template_id=uuid.UUID(int=0), name="inline", version=0, body=ref.inline)
        return None
    template = await session.scalar(
        select(PromptTemplate).where(PromptTemplate.id == ref.template_id, PromptTemplate.workspace_id == workspace_id)
    )
    if template is None:
        raise ValidationFailed(f"Node {node.id}: prompt template not found", details={"node_id": node.id})
    version = ref.version or template.latest_version
    row = await session.scalar(
        select(PromptTemplateVersion).where(
            PromptTemplateVersion.template_id == template.id, PromptTemplateVersion.version == version
        )
    )
    if row is None:
        raise ValidationFailed(f"Node {node.id}: prompt version {version} not found", details={"node_id": node.id})
    return SnapshotPrompt(template_id=template.id, name=template.name, version=version, body=row.body)


async def build_snapshot(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    pipeline: Pipeline,
    version: PipelineVersion,
    started_by_role: Role | None,
) -> ConfigSnapshot:
    graph = PipelineGraph.model_validate(version.graph)
    llm: dict[str, SnapshotLLM] = {}
    prompts: dict[str, SnapshotPrompt] = {}
    for node in graph.nodes:
        if isinstance(node, (LLMNode, AgentNode)):
            llm[node.id] = await _resolve_model(session, workspace_id, node)
            prompt = await _resolve_prompt(session, workspace_id, node)
            if prompt is not None:
                prompts[node.id] = prompt

    servers = {
        s.id: s for s in (await session.scalars(
            select(MCPServer).where(MCPServer.workspace_id == workspace_id, MCPServer.is_active.is_(True))
        )).all()
    }
    tools: dict[str, SnapshotTool] = {}
    if servers:
        rows = (await session.scalars(
            select(MCPTool).where(MCPTool.server_id.in_(servers.keys()), MCPTool.is_stale.is_(False))
        )).all()
        for t in rows:
            server = servers[t.server_id]
            name = namespaced(server.slug, t.name)
            tools[name] = SnapshotTool(
                tool_id=t.id, server_id=server.id, server_slug=server.slug, name=t.name, namespaced_name=name,
                description=t.description or "", input_schema=t.input_schema, schema_hash=t.schema_hash,
                is_enabled=t.is_enabled, is_read_only=t.is_read_only, is_destructive=t.is_destructive,
                requires_approval=t.requires_approval, risk_level=t.risk_level,
            )
    variables = {
        v.key: v.value for v in (await session.scalars(
            select(PromptVariable).where(PromptVariable.workspace_id == workspace_id)
        )).all()
    }
    return ConfigSnapshot(
        pipeline_id=pipeline.id, pipeline_name=pipeline.name, pipeline_version_id=version.id,
        pipeline_version=version.version, graph_hash=version.graph_hash, graph=graph, llm=llm,
        prompts=prompts, variables=variables, tools=tools,
        servers={str(s.id): SnapshotServer(server_id=s.id, slug=s.slug, name=s.name) for s in servers.values()},
        policy=SnapshotPolicy(started_by_role=started_by_role),
        created_at=utcnow(),
    )


def node_types(snapshot: ConfigSnapshot) -> set[NodeType]:
    return {n.type for n in snapshot.graph.nodes}
