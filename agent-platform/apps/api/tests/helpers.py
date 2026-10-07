"""Helpers shared by integration and API tests (DB access, demo runs, graph state)."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import select

from app.core.enums import ApprovalKind, ApprovalStatus, DecisionAction, ToolCallStatus
from app.db.session import session_factory, session_scope
from app.hitl.approvals import decide
from app.models import Approval, Execution, ExecutionEvent, Pipeline, ToolCall
from app.orchestration.compiler import compile_pipeline
from app.orchestration.snapshot import ConfigSnapshot
from app.services.context import AuthContext
from app.services.executions import start_manual

DEMO_INPUT: dict[str, Any] = {"query": "python", "min_hourly_rate": 40}
SUBMIT = "demo_jobs__submit_proposal"


async def demo_pipeline_id() -> uuid.UUID:
    async with session_scope() as session:
        pid = await session.scalar(select(Pipeline.id).where(Pipeline.slug == "job_application_assistant"))
    assert pid is not None
    return pid


async def start_demo(ctx: AuthContext, input: dict[str, Any] | None = None) -> uuid.UUID:
    async with session_scope() as session:
        execution = await start_manual(session, ctx, await demo_pipeline_id(), input or DEMO_INPUT)
    return execution.id


async def db_execution(execution_id: uuid.UUID) -> Execution:
    async with session_scope() as session:
        row = await session.get(Execution, execution_id)
    assert row is not None
    return row


async def tool_calls(execution_id: uuid.UUID) -> list[ToolCall]:
    async with session_scope() as session:
        return list((await session.scalars(select(ToolCall).where(ToolCall.execution_id == execution_id)
                                           .order_by(ToolCall.created_at))).all())


async def approvals(execution_id: uuid.UUID) -> list[Approval]:
    async with session_scope() as session:
        return list((await session.scalars(select(Approval).where(Approval.execution_id == execution_id)
                                           .order_by(Approval.created_at))).all())


async def pending_approval(execution_id: uuid.UUID, kind: ApprovalKind = ApprovalKind.tool_call) -> Approval:
    rows = [a for a in await approvals(execution_id) if a.status == ApprovalStatus.pending and a.kind == kind]
    assert len(rows) == 1, [(a.kind, a.status) for a in await approvals(execution_id)]
    return rows[0]


async def submit_calls(execution_id: uuid.UUID) -> list[ToolCall]:
    return [c for c in await tool_calls(execution_id) if c.namespaced_name == SUBMIT]


async def event_seqs(execution_id: uuid.UUID) -> list[int]:
    async with session_scope() as session:
        return list((await session.scalars(select(ExecutionEvent.seq).where(
            ExecutionEvent.execution_id == execution_id).order_by(ExecutionEvent.seq))).all())


async def graph_values(checkpointer: Any, execution_id: uuid.UUID) -> dict[str, Any]:
    row = await db_execution(execution_id)
    snapshot = ConfigSnapshot.model_validate(row.config_snapshot)
    graph = compile_pipeline(snapshot.graph, checkpointer)
    state = await graph.aget_state({"configurable": {"thread_id": row.thread_id}})
    return dict(state.values)


async def patch_snapshot_tool(execution_id: uuid.UUID, tool: str, **values: Any) -> None:
    async with session_scope() as session:
        row = await session.get(Execution, execution_id)
        assert row is not None
        snapshot = dict(row.config_snapshot)
        tools = dict(snapshot["tools"])
        tools[tool] = {**tools[tool], **values}
        snapshot["tools"] = tools
        await session.execute(sa.update(Execution).where(Execution.id == execution_id)
                              .values(config_snapshot=snapshot))


def statuses(calls: list[ToolCall]) -> dict[str, list[ToolCallStatus]]:
    out: dict[str, list[ToolCallStatus]] = {}
    for call in calls:
        out.setdefault(call.namespaced_name, []).append(call.status)
    return out


async def decide_as(ctx: AuthContext, approval_id: uuid.UUID, action: DecisionAction, **kwargs: Any) -> Approval:
    """Same entry point the API uses (`POST /approvals/{id}/decision`)."""
    async with session_factory()() as session:
        return await decide(session, ctx, approval_id, action=action, **kwargs)
