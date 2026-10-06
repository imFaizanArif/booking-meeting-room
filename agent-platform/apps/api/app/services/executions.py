"""Execution use cases: start (manual, schedule, webhook, restart), list, inspect, control."""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.writer import audit
from app.core.enums import (
    AuditEventType,
    EventType,
    ExecutionStatus,
    Role,
    TriggerKind,
)
from app.core.errors import IllegalTransition, NotFound, ValidationFailed
from app.events.publisher import publish_execution_event
from app.models import (
    Approval,
    Execution,
    ExecutionEvent,
    ExecutionNode,
    LLMUsage,
    Pipeline,
    PipelineVersion,
    ToolCall,
)
from app.orchestration.snapshot import build_snapshot
from app.orchestration.state_machine import can_transition_execution
from app.schemas.pipeline_graph import PipelineGraph, TriggerNode
from app.services.context import Actor, AuthContext
from app.tools.validation import argument_errors
from app.workers.queue import Job, JobQueue, get_queue, resume_job_id


async def prepare_execution(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    pipeline: Pipeline,
    version: PipelineVersion,
    input: dict[str, Any],
    trigger: TriggerKind,
    actor: Actor | AuthContext,
    started_by_role: Role | None,
    triggered_by: uuid.UUID | None = None,
    schedule_id: uuid.UUID | None = None,
    restarted_from_id: uuid.UUID | None = None,
) -> Execution:
    graph = PipelineGraph.model_validate(version.graph)
    trigger_node = next((n for n in graph.nodes if isinstance(n, TriggerNode)), None)
    if trigger_node is None:
        raise ValidationFailed("Pipeline has no trigger")
    allowed = {TriggerKind.manual: trigger_node.config.allow_manual, TriggerKind.schedule: trigger_node.config.allow_schedule,
               TriggerKind.webhook: trigger_node.config.allow_webhook, TriggerKind.restart: True}[trigger]
    if not allowed:
        raise ValidationFailed(f"This pipeline does not accept {trigger.value} triggers")
    errors = argument_errors(trigger_node.config.input_schema, input)
    if errors:
        raise ValidationFailed("Input does not match the pipeline's input schema", details={"fields": errors})
    snapshot = await build_snapshot(session, workspace_id=workspace_id, pipeline=pipeline, version=version,
                                    started_by_role=started_by_role)
    execution_id = uuid.uuid4()
    execution = Execution(
        id=execution_id, workspace_id=workspace_id, pipeline_id=pipeline.id, pipeline_version_id=version.id,
        trigger=trigger, triggered_by=triggered_by, schedule_id=schedule_id, restarted_from_id=restarted_from_id,
        status=ExecutionStatus.queued, input=input, config_snapshot=snapshot.model_dump(mode="json"),
        thread_id=str(execution_id),
    )
    session.add(execution)
    await audit(session, event_type=AuditEventType.execution_started, actor=actor, workspace_id=workspace_id,
                entity_type="execution", entity_id=execution_id, execution_id=execution_id,
                payload={"pipeline": pipeline.name, "version": version.version, "trigger": trigger.value})
    await session.flush()
    return execution


async def dispatch_execution(execution: Execution, queue: JobQueue | None = None) -> None:
    """After commit: announce and enqueue. Safe to repeat (the job id is deterministic)."""
    snapshot = execution.config_snapshot or {}
    await publish_execution_event(workspace_id=execution.workspace_id, execution_id=execution.id,
                                  type=EventType.execution_created,
                                  payload={"pipeline": snapshot.get("pipeline_name"),
                                           "version": snapshot.get("pipeline_version"),
                                           "trigger": execution.trigger.value})
    await (queue or get_queue()).enqueue(Job.run_execution, str(execution.id), job_id=f"run:{execution.id}")


async def create_execution(session: AsyncSession, *, queue: JobQueue | None = None, **kwargs: Any) -> Execution:
    execution = await prepare_execution(session, **kwargs)
    await session.commit()
    await dispatch_execution(execution, queue)
    return execution


async def start_manual(session: AsyncSession, ctx: AuthContext, pipeline_id: uuid.UUID,
                       input: dict[str, Any], version_number: int | None = None) -> Execution:
    ctx.require(Role.operator)
    pipeline = await session.scalar(select(Pipeline).where(Pipeline.id == pipeline_id,
                                                           Pipeline.workspace_id == ctx.workspace_id))
    if pipeline is None:
        raise NotFound("Pipeline not found")
    if version_number is not None:
        version = await session.scalar(select(PipelineVersion).where(
            PipelineVersion.pipeline_id == pipeline.id, PipelineVersion.version == version_number))
    else:
        version = await session.get(PipelineVersion, pipeline.latest_version_id) if pipeline.latest_version_id else None
    if version is None:
        raise ValidationFailed("Save the pipeline before running it")
    return await create_execution(session, workspace_id=ctx.workspace_id, pipeline=pipeline, version=version,
                                  input=input, trigger=TriggerKind.manual, actor=ctx, started_by_role=ctx.role,
                                  triggered_by=ctx.user_id)


async def get_execution(session: AsyncSession, ctx: AuthContext, execution_id: uuid.UUID) -> Execution:
    row = await session.scalar(select(Execution).where(Execution.id == execution_id,
                                                       Execution.workspace_id == ctx.workspace_id))
    if row is None:
        raise NotFound("Execution not found")
    return row


async def list_executions(
    session: AsyncSession, ctx: AuthContext, *, status: list[ExecutionStatus] | None = None,
    pipeline_id: uuid.UUID | None = None, limit: int = 50, offset: int = 0,
) -> tuple[list[tuple[Execution, str]], int]:
    query = select(Execution, Pipeline.name).join(Pipeline, Pipeline.id == Execution.pipeline_id).where(
        Execution.workspace_id == ctx.workspace_id)
    if status:
        query = query.where(Execution.status.in_(status))
    if pipeline_id:
        query = query.where(Execution.pipeline_id == pipeline_id)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = (await session.execute(query.order_by(Execution.created_at.desc()).limit(limit).offset(offset))).all()
    return [(r[0], r[1]) for r in rows], total


async def execution_detail(session: AsyncSession, ctx: AuthContext, execution_id: uuid.UUID) -> dict[str, Any]:
    execution = await get_execution(session, ctx, execution_id)
    pipeline = await session.get(Pipeline, execution.pipeline_id)
    nodes = (await session.scalars(select(ExecutionNode).where(ExecutionNode.execution_id == execution_id)
                                   .order_by(ExecutionNode.started_at.nulls_last(), ExecutionNode.created_at))).all()
    tool_calls = (await session.scalars(select(ToolCall).where(ToolCall.execution_id == execution_id)
                                        .order_by(ToolCall.created_at))).all()
    usage = (await session.scalars(select(LLMUsage).where(LLMUsage.execution_id == execution_id)
                                   .order_by(LLMUsage.created_at))).all()
    approvals = (await session.scalars(select(Approval).where(Approval.execution_id == execution_id)
                                       .order_by(Approval.created_at))).all()
    return {"execution": execution, "pipeline_name": pipeline.name if pipeline else "", "nodes": list(nodes),
            "tool_calls": list(tool_calls), "usage": list(usage), "approvals": list(approvals)}


async def list_events(session: AsyncSession, ctx: AuthContext, execution_id: uuid.UUID, after_seq: int = 0,
                      limit: int = 500) -> list[ExecutionEvent]:
    await get_execution(session, ctx, execution_id)
    return list((await session.scalars(
        select(ExecutionEvent).where(ExecutionEvent.execution_id == execution_id, ExecutionEvent.seq > after_seq)
        .order_by(ExecutionEvent.seq).limit(limit)
    )).all())


async def _transition(session: AsyncSession, execution: Execution, new: ExecutionStatus) -> None:
    if not can_transition_execution(execution.status, new):
        raise IllegalTransition(f"Cannot {new.value} an execution that is {execution.status.value}",
                                details={"from": execution.status.value, "to": new.value})
    changed = await session.scalar(
        sa.update(Execution).where(Execution.id == execution.id, Execution.status == execution.status)
        .values(status=new).returning(Execution.id)
    )
    if changed is None:
        raise IllegalTransition("The execution changed state; refresh and try again")


async def control(session: AsyncSession, ctx: AuthContext, execution_id: uuid.UUID, action: str) -> Execution:
    """pause | resume | cancel | retry. Restart is a separate use case (new execution)."""
    ctx.require(Role.operator)
    execution = await get_execution(session, ctx, execution_id)
    enqueue = False
    operator_resume = False
    if action == "pause":
        if execution.status not in (ExecutionStatus.queued, ExecutionStatus.running, ExecutionStatus.resuming,
                                    ExecutionStatus.waiting_for_tool):
            raise IllegalTransition(f"Cannot pause an execution that is {execution.status.value}")
        execution.pause_requested = True
    elif action == "resume":
        if execution.status != ExecutionStatus.paused:
            raise IllegalTransition(f"Cannot resume an execution that is {execution.status.value}")
        execution.pause_requested = False
        await _transition(session, execution, ExecutionStatus.resuming)
        enqueue, operator_resume = True, True
    elif action == "retry":
        if execution.status != ExecutionStatus.failed:
            raise IllegalTransition("Only failed executions can be retried from the failed node")
        execution.error = None
        await _transition(session, execution, ExecutionStatus.resuming)
        enqueue = True
    elif action == "cancel":
        if execution.status in (ExecutionStatus.completed, ExecutionStatus.cancelled):
            raise IllegalTransition(f"Execution is already {execution.status.value}")
        execution.cancel_requested = True
        if execution.status in (ExecutionStatus.paused_for_review, ExecutionStatus.paused,
                                ExecutionStatus.failed):
            # Nothing is running: the worker finalises cancellation (open calls, approvals) on pickup.
            await _transition(session, execution, ExecutionStatus.resuming)
            enqueue = True
        elif execution.status in (ExecutionStatus.queued, ExecutionStatus.waiting_for_timer):
            enqueue = True
    else:
        raise ValidationFailed(f"Unknown action {action}")
    await audit(session, event_type=AuditEventType.execution_control, actor=ctx, workspace_id=ctx.workspace_id,
                entity_type="execution", entity_id=execution.id, execution_id=execution.id,
                payload={"action": action})
    await session.commit()
    if enqueue:
        await get_queue().enqueue(Job.resume_execution, str(execution.id),
                                  {"operator_resume": operator_resume}, job_id=resume_job_id(execution.id))
    return await get_execution(session, ctx, execution_id)


async def restart(session: AsyncSession, ctx: AuthContext, execution_id: uuid.UUID) -> Execution:
    ctx.require(Role.operator)
    previous = await get_execution(session, ctx, execution_id)
    pipeline = await session.get(Pipeline, previous.pipeline_id)
    version = await session.get(PipelineVersion, previous.pipeline_version_id)
    assert pipeline is not None and version is not None
    return await create_execution(session, workspace_id=ctx.workspace_id, pipeline=pipeline, version=version,
                                  input=previous.input, trigger=TriggerKind.restart, actor=ctx,
                                  started_by_role=ctx.role, triggered_by=ctx.user_id, restarted_from_id=previous.id)
