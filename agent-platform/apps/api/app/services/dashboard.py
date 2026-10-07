"""Operational numbers for the dashboard and the audit search."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovalStatus, ExecutionStatus, ServerStatus
from app.core.time import utcnow
from app.models import AuditEvent, Execution, LLMUsage, MCPServer, Pipeline, Schedule
from app.schemas.runtime import AuditOut, DashboardOut, DashboardSchedule, DashboardServer, ExecutionOut
from app.services.approvals import list_approvals
from app.services.context import AuthContext

_RUNNING = [
    ExecutionStatus.queued,
    ExecutionStatus.running,
    ExecutionStatus.resuming,
    ExecutionStatus.waiting_for_tool,
    ExecutionStatus.paused_for_review,
    ExecutionStatus.paused,
    ExecutionStatus.waiting_for_timer,
]


async def execution_outs(session: AsyncSession, rows: list[Execution]) -> list[ExecutionOut]:
    names = (
        dict(
            (
                await session.execute(
                    select(Pipeline.id, Pipeline.name).where(Pipeline.id.in_({r.pipeline_id for r in rows}))
                )
            ).all()
        )
        if rows
        else {}
    )
    out = []
    for r in rows:
        item = ExecutionOut.model_validate(r)
        item.pipeline_name = names.get(r.pipeline_id, "")
        item.pipeline_version = int((r.config_snapshot or {}).get("pipeline_version") or 0)
        out.append(item)
    return out


async def dashboard(session: AsyncSession, ctx: AuthContext) -> DashboardOut:
    ws = ctx.workspace_id
    since = utcnow() - timedelta(hours=24)
    running = list(
        (
            await session.scalars(
                select(Execution)
                .where(Execution.workspace_id == ws, Execution.status.in_(_RUNNING))
                .order_by(Execution.created_at.desc())
                .limit(20)
            )
        ).all()
    )
    failures = list(
        (
            await session.scalars(
                select(Execution)
                .where(
                    Execution.workspace_id == ws,
                    Execution.status == ExecutionStatus.failed,
                    Execution.updated_at >= since,
                )
                .order_by(Execution.updated_at.desc())
                .limit(10)
            )
        ).all()
    )
    pending, _ = await list_approvals(session, ctx, status=ApprovalStatus.pending, limit=10)
    servers = (
        await session.scalars(
            select(MCPServer).where(
                MCPServer.workspace_id == ws,
                MCPServer.is_active.is_(True),
                MCPServer.status.in_([ServerStatus.failed, ServerStatus.reconnecting]),
            )
        )
    ).all()
    schedules = (
        await session.execute(
            select(Schedule, Pipeline.name)
            .join(Pipeline, Pipeline.id == Schedule.pipeline_id)
            .where(Schedule.workspace_id == ws, Schedule.is_active.is_(True))
            .order_by(Schedule.next_run_at.nulls_last())
            .limit(5)
        )
    ).all()
    usage = (
        await session.execute(
            select(
                func.coalesce(func.sum(LLMUsage.estimated_cost), 0), func.coalesce(func.sum(LLMUsage.total_tokens), 0)
            ).where(LLMUsage.workspace_id == ws, LLMUsage.created_at >= since)
        )
    ).one()
    counts = dict(
        (
            await session.execute(
                select(Execution.status, func.count())
                .where(Execution.workspace_id == ws, Execution.created_at >= since)
                .group_by(Execution.status)
            )
        ).all()
    )
    return DashboardOut(
        running=await execution_outs(session, running),
        pending_approvals=pending,
        unhealthy_servers=[
            DashboardServer(id=s.id, name=s.name, status=s.status, status_message=s.status_message) for s in servers
        ],
        next_runs=[
            DashboardSchedule(id=s.id, name=s.name, pipeline_name=name, next_run_at=s.next_run_at)
            for s, name in schedules
        ],
        recent_failures=await execution_outs(session, failures),
        cost_24h=Decimal(usage[0]),
        tokens_24h=int(usage[1]),
        executions_24h=sum(counts.values()),
        status_counts_24h={k.value if hasattr(k, "value") else str(k): v for k, v in counts.items()},
    )


async def search_audit(
    session: AsyncSession,
    ctx: AuthContext,
    *,
    q: str | None = None,
    event_type: str | None = None,
    entity_type: str | None = None,
    execution_id: uuid.UUID | None = None,
    actor: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[AuditOut], int]:
    query = select(AuditEvent).where(AuditEvent.workspace_id == ctx.workspace_id)
    if event_type:
        query = query.where(AuditEvent.event_type == event_type)
    if entity_type:
        query = query.where(AuditEvent.entity_type == entity_type)
    if execution_id:
        query = query.where(AuditEvent.execution_id == execution_id)
    if actor:
        query = query.where(AuditEvent.actor_label.ilike(f"%{actor}%"))
    if since:
        query = query.where(AuditEvent.created_at >= since)
    if until:
        query = query.where(AuditEvent.created_at <= until)
    if q:
        like = f"%{q}%"
        query = query.where(
            AuditEvent.event_type.ilike(like) | AuditEvent.entity_id.ilike(like) | AuditEvent.actor_label.ilike(like)
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (await session.scalars(query.order_by(AuditEvent.created_at.desc()).limit(limit).offset(offset))).all()
    return [AuditOut.model_validate(r) for r in rows], total
