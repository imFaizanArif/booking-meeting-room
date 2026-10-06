"""Approval desk queries. Decisions live in app.hitl.approvals."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ApprovalStatus
from app.core.errors import NotFound
from app.models import Approval, Execution, Pipeline, ToolCall, User
from app.orchestration.snapshot import ConfigSnapshot
from app.schemas.runtime import ApprovalDetail, ApprovalOut, ToolCallOut
from app.services.context import AuthContext


async def _enrich(session: AsyncSession, rows: list[Approval]) -> list[ApprovalOut]:
    if not rows:
        return []
    exec_ids = {r.execution_id for r in rows}
    pipelines = dict((await session.execute(
        select(Execution.id, Pipeline.name).join(Pipeline, Pipeline.id == Execution.pipeline_id)
        .where(Execution.id.in_(exec_ids)))).all())
    call_ids = [r.tool_call_id for r in rows if r.tool_call_id]
    calls = {c.id: c for c in (await session.scalars(select(ToolCall).where(ToolCall.id.in_(call_ids)))).all()} \
        if call_ids else {}
    user_ids = {r.decided_by for r in rows if r.decided_by}
    emails = dict((await session.execute(select(User.id, User.email).where(User.id.in_(user_ids)))).all()) \
        if user_ids else {}
    out = []
    for row in rows:
        item = ApprovalOut.model_validate(row)
        item.pipeline_name = pipelines.get(row.execution_id, "")
        call = calls.get(row.tool_call_id) if row.tool_call_id else None
        if call is not None:
            item.tool_name = call.tool_name
            item.server_slug = call.namespaced_name.split("__", 1)[0]
        item.decided_by_email = emails.get(row.decided_by) if row.decided_by else None
        out.append(item)
    return out


async def list_approvals(session: AsyncSession, ctx: AuthContext, *, status: ApprovalStatus | None = None,
                         execution_id: uuid.UUID | None = None, limit: int = 100,
                         offset: int = 0) -> tuple[list[ApprovalOut], int]:
    query = select(Approval).where(Approval.workspace_id == ctx.workspace_id)
    if status is not None:
        query = query.where(Approval.status == status)
    if execution_id is not None:
        query = query.where(Approval.execution_id == execution_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    order = Approval.created_at.asc() if status == ApprovalStatus.pending else Approval.created_at.desc()
    rows = list((await session.scalars(query.order_by(order).limit(limit).offset(offset))).all())
    return await _enrich(session, rows), total


async def approval_detail(session: AsyncSession, ctx: AuthContext, approval_id: uuid.UUID) -> ApprovalDetail:
    row = await session.scalar(select(Approval).where(Approval.id == approval_id,
                                                      Approval.workspace_id == ctx.workspace_id))
    if row is None:
        raise NotFound("Approval not found")
    base = (await _enrich(session, [row]))[0]
    detail = ApprovalDetail(**base.model_dump())
    execution = await session.get(Execution, row.execution_id)
    if row.tool_call_id:
        call = await session.get(ToolCall, row.tool_call_id)
        if call is not None:
            detail.tool_call = ToolCallOut.model_validate(call)
            if execution is not None:
                snapshot = ConfigSnapshot.model_validate(execution.config_snapshot)
                tool = snapshot.tools.get(call.namespaced_name)
                detail.input_schema = tool.input_schema if tool else None
            prior = (await session.scalars(select(ToolCall).where(
                ToolCall.execution_id == row.execution_id, ToolCall.node_id == row.node_id,
                ToolCall.call_seq < call.call_seq).order_by(ToolCall.call_seq.desc()).limit(8))).all()
            detail.context = [_step(c) for c in reversed(prior)]
    chain: list[Approval] = []
    cursor = row
    seen = {row.id}
    while True:  # walk back through superseded proposals
        previous = await session.scalar(select(Approval).where(Approval.superseded_by == cursor.id))
        if previous is None or previous.id in seen:
            break
        chain.append(previous)
        seen.add(previous.id)
        cursor = previous
    detail.history = await _enrich(session, chain)
    return detail


def _step(call: ToolCall) -> dict[str, Any]:
    result = call.result or {}
    preview = (result.get("content") or "")[:600]
    return {"tool": call.namespaced_name, "status": call.status.value, "arguments": call.arguments,
            "result_preview": preview, "at": call.created_at.isoformat()}
