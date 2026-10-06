"""Demo data: default workspace, admin, providers, mock MCP servers, prompts and the
"Job Application Assistant" pipeline. Idempotent: rerunning updates by name.

Everything here is data. The fake provider's scripted behaviour lives in the pipeline's
node config (`provider_extras.fake`), so switching a node to a real model in the UI is the
only change needed to run the demo against OpenAI, Anthropic or Ollama.
"""

from __future__ import annotations

import os
import sys
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import (
    IsolationMode,
    ProviderType,
    Role,
    ScheduleKind,
    TransportType,
)
from app.core.logging import get_logger
from app.core.security import hash_password
from app.core.time import utcnow
from app.mcp.discovery import upsert_tools
from app.mcp.manager import MCPConnectionManager
from app.mcp.specs import build_spec, compute_config_hash
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
    Schedule,
    User,
    Workspace,
    WorkspaceMember,
)
from app.prompts.render import referenced_variables
from app.scheduler.timing import next_fire
from app.services.pipelines import graph_hash

log = get_logger(__name__)
DEMO_PIPELINE = "Job Application Assistant"


async def _one(session: AsyncSession, model: Any, **where: Any) -> Any:
    query = select(model)
    for key, value in where.items():
        query = query.where(getattr(model, key) == value)
    return await session.scalar(query)


async def seed_identity(session: AsyncSession) -> Workspace:
    settings = get_settings()
    ws = await _one(session, Workspace, slug="default")
    if ws is None:
        ws = Workspace(name="Default workspace", slug="default", settings={})
        session.add(ws)
        await session.flush()
    users = [
        (settings.demo_admin_email, "Admin", settings.demo_admin_password.get_secret_value(), Role.owner),
        ("operator@example.com", "Operator", "operator-password", Role.operator),
        ("viewer@example.com", "Viewer", "viewer-password", Role.viewer),
    ]
    for email, name, password, role in users:
        user = await _one(session, User, email=email)
        if user is None:
            user = User(email=email, display_name=name, password_hash=hash_password(password))
            session.add(user)
            await session.flush()
        if await _one(session, WorkspaceMember, workspace_id=ws.id, user_id=user.id) is None:
            session.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=role))
    await session.flush()
    return ws


async def _provider(session: AsyncSession, ws: Workspace, name: str, ptype: ProviderType, base_url: str | None,
                    active: bool) -> LLMProvider:
    row = await _one(session, LLMProvider, workspace_id=ws.id, name=name)
    if row is None:
        row = LLMProvider(workspace_id=ws.id, name=name, provider_type=ptype, base_url=base_url, is_active=active,
                          metadata_={})
        session.add(row)
        await session.flush()
    return row


async def _model(session: AsyncSession, ws: Workspace, provider: LLMProvider, model_name: str, display: str,
                 **kw: Any) -> LLMModel:
    row = await _one(session, LLMModel, provider_id=provider.id, model_name=model_name)
    if row is None:
        row = LLMModel(workspace_id=ws.id, provider_id=provider.id, model_name=model_name, display_name=display, **kw)
        session.add(row)
        await session.flush()
    return row


async def seed_llm(session: AsyncSession, ws: Workspace) -> dict[str, LLMModel]:
    fake = await _provider(session, ws, "Offline fake", ProviderType.fake, None, True)
    openai = await _provider(session, ws, "OpenAI", ProviderType.openai, "https://api.openai.com/v1", False)
    anthropic = await _provider(session, ws, "Anthropic", ProviderType.anthropic, None, False)
    ollama = await _provider(session, ws, "Ollama (local)", ProviderType.ollama, "http://localhost:11434", False)
    models = {
        "filter": await _model(session, ws, fake, "fake-filter", "Fake · filter model", context_window=32_000,
                               supports_json_schema=True),
        "writer": await _model(session, ws, fake, "fake-writer", "Fake · writer model", context_window=32_000),
        "opus": await _model(
            session, ws, anthropic, "claude-opus-5-5", "Claude Opus 5.5", context_window=1_000_000,
            input_price_per_mtok=Decimal("4"), output_price_per_mtok=Decimal("20"),
            default_parameters={"max_tokens": 16000, "extras": {"anthropic": {
                "thinking": {"type": "adaptive"}, "output_config": {"effort": "medium"}, "fallbacks": "default"}}}),
        "sonnet": await _model(
            session, ws, anthropic, "claude-sonnet-5-5", "Claude Sonnet 5.5", context_window=1_000_000,
            input_price_per_mtok=Decimal("2"), output_price_per_mtok=Decimal("10"),
            default_parameters={"max_tokens": 16000, "extras": {"anthropic": {"thinking": {"type": "adaptive"}}}}),
        "gpt": await _model(session, ws, openai, "gpt-4.1-mini", "GPT-4.1 mini", context_window=1_000_000,
                            input_price_per_mtok=Decimal("0.4"), output_price_per_mtok=Decimal("1.6")),
        "llama": await _model(session, ws, ollama, "llama3.2", "Llama 3.2 (Ollama)", context_window=128_000,
                              supports_json_schema=True),
    }
    if not await session.scalar(select(LLMModel.id).where(LLMModel.workspace_id == ws.id,
                                                          LLMModel.is_default.is_(True))):
        models["writer"].is_default = True
    await session.flush()
    return models


def _python() -> str:
    return os.environ.get("MOCK_MCP_PYTHON") or sys.executable


async def seed_mcp(session: AsyncSession, ws: Workspace) -> list[MCPServer]:
    jobs_url = os.environ.get("MOCK_JOBS_URL", "http://127.0.0.1:8811/mcp")
    specs = [
        ("Demo Jobs", "demo_jobs", TransportType.streamable_http, None, [], jobs_url,
         "Job board: search listings and submit proposals (Streamable HTTP)."),
        ("Demo Calendar", "demo_calendar", TransportType.stdio, _python(), ["-m", "mock_mcp.calendar_server"], None,
         "Calendar availability and events (stdio)."),
        ("Demo GitHub", "demo_github", TransportType.stdio, _python(), ["-m", "mock_mcp.github_server"], None,
         "Repositories and issues (stdio)."),
    ]
    servers = []
    for name, slug, transport, command, args, url, description in specs:
        row = await _one(session, MCPServer, workspace_id=ws.id, slug=slug)
        if row is None:
            row = MCPServer(workspace_id=ws.id, slug=slug, name=name)
            session.add(row)
        row.description, row.transport, row.command, row.args, row.url = description, transport, command, args, url
        row.isolation, row.is_active = IsolationMode.shared, True
        row.command_confirmed_at = utcnow() if transport == TransportType.stdio else None
        row.env_refs = row.env_refs or {}
        await session.flush()
        row.config_hash = compute_config_hash(row)
        servers.append(row)
    await session.flush()
    return servers


async def discover_and_enable(session: AsyncSession, servers: list[MCPServer]) -> list[str]:
    """Connect to each mock server, discover tools and enable them (approval flags keep their safe defaults)."""
    manager = MCPConnectionManager()
    problems = []
    try:
        for server in servers:
            try:
                conn = await manager.get(await build_spec(session, server))
            except Exception as exc:  # noqa: BLE001 - seed continues, discovery can be re-run from the UI
                problems.append(f"{server.slug}: {exc}")
                continue
            await upsert_tools(session, server, list(conn.tools.values()))
            await session.flush()
            for tool in (await session.scalars(select(MCPTool).where(MCPTool.server_id == server.id))).all():
                tool.is_enabled = True
    finally:
        await manager.shutdown()
    await session.flush()
    return problems


PROMPTS = {
    "Job filter": (
        "Selects promising job listings for a freelancer.",
        "You screen freelance job listings for {{ my_name }}.\n"
        "Keep only listings that pay at least {{ target_hourly_rate }} USD per hour and match these skills: "
        "{{ my_skills }}.\nReturn at most two listings, best first, as JSON."),
    "Proposal writer": (
        "Drafts and submits a proposal with tools. Submission always needs human approval.",
        "You write concise, specific proposals for {{ my_name }}.\n"
        "Resume:\n{{ my_resume }}\n\n"
        "Use the job board tools: read the job with get_job, then submit one proposal with submit_proposal. "
        "Quote the hourly rate {{ target_hourly_rate }}. Mention one relevant repository by name."),
}

VARIABLES = {
    "my_name": ("Sam Rivera", "Name used in proposals"),
    "my_skills": ("python, fastapi, postgres, llm, mcp, typescript", "Comma separated skills"),
    "target_hourly_rate": ("85", "Minimum hourly rate in USD"),
    "my_resume": ("Backend engineer, 9 years. Built agent tooling with MCP and human-in-the-loop review. "
                  "Python, FastAPI, Postgres, TypeScript.", "Short resume"),
}


async def seed_prompts(session: AsyncSession, ws: Workspace) -> dict[str, PromptTemplate]:
    for key, (value, description) in VARIABLES.items():
        if await _one(session, PromptVariable, workspace_id=ws.id, key=key) is None:
            session.add(PromptVariable(workspace_id=ws.id, key=key, value=value, description=description))
    templates = {}
    for name, (description, body) in PROMPTS.items():
        row = await _one(session, PromptTemplate, workspace_id=ws.id, name=name)
        if row is None:
            row = PromptTemplate(workspace_id=ws.id, name=name, description=description, latest_version=1)
            session.add(row)
            await session.flush()
            session.add(PromptTemplateVersion(template_id=row.id, version=1, body=body,
                                              variables=sorted(referenced_variables(body)),
                                              change_note="Seeded"))
        templates[name] = row
    await session.flush()
    return templates


# Fake-provider scripts (Jinja rendered to JSON per step; see app.llm.adapters.fake).
FILTER_SCRIPT = [
    '{"json": {"shortlist": {{ ((input.jobs | selectattr("hourly_rate", "ge", input.target_hourly_rate | int)'
    ' | list)[:2]) | tojson }} }}'
]
ANALYSE_SCRIPT = [
    '{"content": {{ ("Fit for " ~ input.title ~ " (" ~ input.client ~ "): skills " ~ (input.skills | join(", "))'
    ' ~ "; rate " ~ input.hourly_rate ~ " USD/h. Strong match on backend and integration work.") | tojson }} }'
]
WRITER_SCRIPT = [
    '{"content": "Reading the top listing first.", "tool_calls": [{"name": "demo_jobs__get_job",'
    ' "arguments": {"job_id": {{ input.jobs[0].id | tojson }} }}]}',
    '{"content": "Drafting the proposal.", "tool_calls": [{"name": "demo_jobs__submit_proposal", "arguments": {'
    '"job_id": {{ last_tool_result.id | tojson }}, "hourly_rate": {{ input.rate | int }},'
    ' "cover_letter": {{ ("Hi " ~ last_tool_result.client ~ ", I build production APIs and agent tooling. For \\""'
    ' ~ last_tool_result.title ~ "\\" I would start with the data model and a thin vertical slice. Relevant work: "'
    ' ~ (input.repos[0].repositories[0].name if input.repos and input.repos[0].repositories else "shipment-tracker")'
    ' ~ ". Rate: " ~ input.rate ~ " USD/h.") | tojson }} }}]}',
    '{% if last_tool_result is mapping and last_tool_result.get("reviewer_requested_new_proposal") %}'
    '{"content": "Revising per reviewer feedback.", "tool_calls": [{"name": "demo_jobs__submit_proposal",'
    ' "arguments": {"job_id": {{ input.jobs[0].id | tojson }}, "hourly_rate": {{ input.rate | int }},'
    ' "cover_letter": {{ ("Revised proposal. " ~ last_tool_result.get("feedback", "") ~ " I can start next week and'
    ' share a plan within two days.") | tojson }} }}]}'
    '{% elif last_tool_result is mapping and last_tool_result.get("rejected") %}'
    '{"content": {{ ("The proposal was not submitted: " ~ last_tool_result.get("reason", "")) | tojson }} }'
    '{% else %}'
    '{"content": {{ ("Submitted proposal " ~ (last_tool_result.get("proposal_id", "") if last_tool_result is mapping'
    ' else "") ~ ".") | tojson }} }'
    '{% endif %}',
    '{% if last_tool_result is mapping and last_tool_result.get("proposal_id") %}'
    '{"content": {{ ("Submitted revised proposal " ~ last_tool_result.get("proposal_id") ~ ".") | tojson }} }'
    '{% else %}{"content": "Finished without submitting."}{% endif %}',
]


def demo_graph(models: dict[str, LLMModel], templates: dict[str, PromptTemplate]) -> dict[str, Any]:
    shortlist_schema = {
        "type": "object", "required": ["shortlist"],
        "properties": {"shortlist": {"type": "array", "maxItems": 5, "items": {
            "type": "object", "required": ["id", "title", "hourly_rate"],
            "properties": {"id": {"type": "string"}, "title": {"type": "string"},
                           "hourly_rate": {"type": "number"}, "skills": {"type": "array"}}}}},
    }
    return {
        "nodes": [
            {"id": "trigger", "type": "trigger", "name": "Daily trigger", "position": {"x": 0, "y": 160},
             "config": {"input_schema": {"type": "object", "properties": {
                 "query": {"type": "string", "default": "python"},
                 "min_hourly_rate": {"type": "integer", "default": 40}}},
                 "allow_manual": True, "allow_schedule": True, "allow_webhook": True}},
            {"id": "search_jobs", "type": "mcp_tool", "name": "Search jobs", "position": {"x": 240, "y": 160},
             "config": {"tool": "demo_jobs__search_jobs",
                        "arguments": {"query": "=get(input, 'query', 'python')",
                                      "min_hourly_rate": "=get(input, 'min_hourly_rate', 40)", "limit": 10}}},
            {"id": "filter", "type": "llm", "name": "Filter listings", "position": {"x": 480, "y": 160},
             "config": {"model_id": str(models["filter"].id),
                        "system_prompt": {"template_id": str(templates["Job filter"].id)},
                        "user_prompt": '{{ {"jobs": nodes.search_jobs.output.jobs, '
                                       '"target_hourly_rate": target_hourly_rate} | tojson }}',
                        "output_schema": shortlist_schema,
                        "provider_extras": {"fake": {"script": FILTER_SCRIPT}}}},
            {"id": "analyse", "type": "llm", "name": "Analyse each job", "position": {"x": 760, "y": 0},
             "map": {"over": "nodes.filter.output.shortlist", "concurrency": 4, "item_name": "item"},
             "config": {"model_id": str(models["filter"].id),
                        "system_prompt": {"inline": "Summarise how well this job fits {{ my_name }} in two sentences."},
                        "user_prompt": "{{ item | tojson }}",
                        "provider_extras": {"fake": {"script": ANALYSE_SCRIPT}}}},
            {"id": "availability", "type": "mcp_tool", "name": "Check availability", "position": {"x": 760, "y": 160},
             "map": {"over": "nodes.filter.output.shortlist", "concurrency": 4, "item_name": "item"},
             "config": {"tool": "demo_calendar__check_availability",
                        "arguments": {"hours_per_week": "=item.hours_per_week", "weeks": 4}}},
            {"id": "repos", "type": "mcp_tool", "name": "Find relevant repos", "position": {"x": 760, "y": 320},
             "map": {"over": "nodes.filter.output.shortlist", "concurrency": 4, "item_name": "item"},
             "config": {"tool": "demo_github__list_repositories", "arguments": {"topic": "=first(item.skills)"}}},
            {"id": "has_fit", "type": "condition", "name": "Any job fits?", "position": {"x": 1040, "y": 160},
             "config": {"expression": "len(nodes.filter.output.shortlist) > 0 and "
                                      "any_of(pluck(nodes.availability.output, 'fits_all_weeks'))"}},
            {"id": "draft", "type": "agent", "name": "Draft & submit proposal", "position": {"x": 1300, "y": 100},
             "config": {"model_id": str(models["writer"].id),
                        "system_prompt": {"template_id": str(templates["Proposal writer"].id)},
                        "user_prompt": '{{ {"jobs": nodes.filter.output.shortlist, "analyses": nodes.analyse.output,'
                                       ' "availability": nodes.availability.output, "repos": nodes.repos.output,'
                                       ' "rate": target_hourly_rate} | tojson }}',
                        "tool_allowlist": ["demo_jobs__get_job", "demo_jobs__submit_proposal"],
                        "max_iterations": 6, "max_tool_calls": 6, "token_budget": 80000,
                        "provider_extras": {"fake": {"script": WRITER_SCRIPT}}}},
            {"id": "done", "type": "end", "name": "Result", "position": {"x": 1580, "y": 100},
             "config": {"output": {"proposal": "=nodes.draft.output", "shortlist": "=nodes.filter.output.shortlist"}}},
            {"id": "nothing", "type": "end", "name": "No fit", "position": {"x": 1300, "y": 300},
             "config": {"output": {"message": "No listing fits right now",
                                   "searched": "=len(nodes.search_jobs.output.jobs)"}}},
        ],
        "edges": [
            {"id": "e1", "source": "trigger", "target": "search_jobs"},
            {"id": "e2", "source": "search_jobs", "target": "filter"},
            {"id": "e3", "source": "filter", "target": "analyse"},
            {"id": "e4", "source": "filter", "target": "availability"},
            {"id": "e5", "source": "filter", "target": "repos"},
            {"id": "e6", "source": "analyse", "target": "has_fit"},
            {"id": "e7", "source": "availability", "target": "has_fit"},
            {"id": "e8", "source": "repos", "target": "has_fit"},
            {"id": "e9", "source": "has_fit", "target": "draft", "branch": "true"},
            {"id": "e10", "source": "has_fit", "target": "nothing", "branch": "false"},
            {"id": "e11", "source": "draft", "target": "done"},
        ],
    }


async def seed_pipeline(session: AsyncSession, ws: Workspace, models: dict[str, LLMModel],
                        templates: dict[str, PromptTemplate]) -> Pipeline:
    from app.schemas.pipeline_graph import PipelineGraph

    graph = PipelineGraph.model_validate(demo_graph(models, templates)).model_dump(mode="json")
    digest = graph_hash(graph)
    pipeline = await _one(session, Pipeline, workspace_id=ws.id, slug="job_application_assistant")
    if pipeline is None:
        pipeline = Pipeline(workspace_id=ws.id, name=DEMO_PIPELINE, slug="job_application_assistant",
                            description="Search jobs, shortlist with one model, check calendar and repos, draft with "
                                        "another model, submit only after human approval.")
        session.add(pipeline)
        await session.flush()
    current = await session.get(PipelineVersion, pipeline.latest_version_id) if pipeline.latest_version_id else None
    if current is None or current.graph_hash != digest:
        version = PipelineVersion(pipeline_id=pipeline.id, version=pipeline.latest_version_number + 1, graph=graph,
                                  graph_hash=digest, change_note="Seeded demo")
        session.add(version)
        await session.flush()
        pipeline.latest_version_id = version.id
        pipeline.latest_version_number = version.version
    if await _one(session, Schedule, pipeline_id=pipeline.id) is None:
        session.add(Schedule(
            workspace_id=ws.id, pipeline_id=pipeline.id, name="Weekday mornings", kind=ScheduleKind.cron,
            cron="45 8 * * 1-5", timezone="Europe/London", input={"query": "python", "min_hourly_rate": 40},
            is_active=False, next_run_at=next_fire(ScheduleKind.cron, after=utcnow(), cron="45 8 * * 1-5",
                                                   interval_seconds=None, daily_time=None, timezone="Europe/London"),
        ))
    await session.flush()
    return pipeline


async def seed_all(session: AsyncSession, *, discover: bool = True) -> dict[str, Any]:
    ws = await seed_identity(session)
    models = await seed_llm(session, ws)
    servers = await seed_mcp(session, ws)
    await session.commit()
    problems = await discover_and_enable(session, servers) if discover else []
    templates = await seed_prompts(session, ws)
    pipeline = await seed_pipeline(session, ws, models, templates)
    await session.commit()
    return {"workspace_id": str(ws.id), "pipeline_id": str(pipeline.id), "problems": problems,
            "models": {k: str(v.id) for k, v in models.items()}, "seed_run": str(uuid.uuid4())}
