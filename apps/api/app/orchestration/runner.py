"""ExecutionRunner: one start/resume pass of an execution inside a worker.

Lease: an execution is driven by at most one worker at a time (`lease_owner`,
`lease_expires_at`, extended by a heartbeat). Without the lease the job yields.

State: LangGraph's checkpoint (thread id = execution id) is the only resumable state. The
runner never rebuilds state from the read model.

Pause/cancel: checked between super-steps (stream_mode="checkpoints"), so no in-flight
tool call is ever cut off by an operator pause. Cancellation is also checked inside nodes
at tool-call boundaries.
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import uuid
from datetime import timedelta
from typing import Any

import sqlalchemy as sa
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command
from sqlalchemy import or_, select

from app.audit.writer import audit
from app.core.config import get_settings
from app.core.enums import (
    ApprovalStatus,
    AuditEventType,
    ExecutionStatus,
    InterruptKind,
    NodeType,
    ToolCallStatus,
)
from app.core.errors import AppError, ExecutionCancelled
from app.core.logging import bind_context, clear_context, get_logger
from app.core.time import utcnow
from app.db.session import session_scope
from app.mcp.manager import MCPConnectionManager
from app.models import Approval, DurableTimer, Execution, ToolCall
from app.notifications.dispatcher import NotificationDispatcher
from app.orchestration.compiler import compile_pipeline
from app.orchestration.llm_service import LLMService
from app.orchestration.nodes.base import error_dict
from app.orchestration.read_model import set_execution_status
from app.orchestration.runtime import RUNTIME_KEY, RuntimeContext
from app.orchestration.snapshot import ConfigSnapshot
from app.ratelimit.limiter import ConcurrencyLimiter, TokenBucket
from app.services.context import WORKER_ACTOR
from app.tools.router import ToolRouter
from app.workers.queue import Job, JobQueue, resume_job_id

log = get_logger(__name__)
_PICKUP = (
    ExecutionStatus.queued,
    ExecutionStatus.resuming,
    ExecutionStatus.running,
    ExecutionStatus.waiting_for_tool,
    ExecutionStatus.waiting_for_timer,
)
_MAX_PASSES = 20


def worker_identity() -> str:
    return f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"


class ExecutionRunner:
    def __init__(
        self,
        *,
        checkpointer: BaseCheckpointSaver[Any],
        connections: MCPConnectionManager,
        queue: JobQueue | None,
        worker_id: str | None = None,
        bucket: TokenBucket | None = None,
        concurrency: ConcurrencyLimiter | None = None,
        notifications: NotificationDispatcher | None = None,
    ) -> None:
        self.checkpointer = checkpointer
        self.connections = connections
        self.queue = queue
        self.worker_id = worker_id or worker_identity()
        self.bucket = bucket
        self.concurrency = concurrency
        self.notifications = notifications or NotificationDispatcher()
        settings = get_settings()
        self.lease_s = settings.worker_lease_seconds
        self.heartbeat_s = settings.worker_heartbeat_seconds

    # ---- lease ----------------------------------------------------------------------------
    async def _acquire(self, execution_id: uuid.UUID) -> Execution | None:
        now = utcnow()
        async with session_scope() as session:
            row = await session.scalar(
                sa.update(Execution)
                .where(
                    Execution.id == execution_id,
                    Execution.status.in_(_PICKUP),
                    or_(
                        Execution.lease_expires_at.is_(None),
                        Execution.lease_expires_at < now,
                        Execution.lease_owner == self.worker_id,
                    ),
                )
                .values(lease_owner=self.worker_id, lease_expires_at=now + timedelta(seconds=self.lease_s))
                .returning(Execution)
            )
            return row

    async def _heartbeat(self, execution_id: uuid.UUID) -> None:
        while True:
            await asyncio.sleep(self.heartbeat_s)
            async with session_scope() as session:
                await session.execute(
                    sa.update(Execution)
                    .where(Execution.id == execution_id, Execution.lease_owner == self.worker_id)
                    .values(lease_expires_at=utcnow() + timedelta(seconds=self.lease_s))
                )

    async def _release(self, execution_id: uuid.UUID) -> None:
        async with session_scope() as session:
            await session.execute(
                sa.update(Execution)
                .where(Execution.id == execution_id, Execution.lease_owner == self.worker_id)
                .values(lease_owner=None, lease_expires_at=None)
            )

    # ---- entry ------------------------------------------------------------------------------
    async def run(self, execution_id: uuid.UUID, *, operator_resume: bool = False) -> ExecutionStatus | None:
        execution = await self._acquire(execution_id)
        if execution is None:
            await self._yield_if_busy(execution_id)
            return None
        bind_context(
            execution_id=execution_id,
            workspace_id=execution.workspace_id,
            pipeline_version_id=execution.pipeline_version_id,
        )
        heartbeat = asyncio.create_task(self._heartbeat(execution_id))
        try:
            return await self._drive(execution, operator_resume=operator_resume)
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
            await self._release(execution_id)
            await self.connections.release_execution(execution_id)
            clear_context()

    async def _yield_if_busy(self, execution_id: uuid.UUID) -> None:
        """Another worker holds the lease: retry shortly so a fresh decision is not lost."""
        async with session_scope() as session:
            row = await session.get(Execution, execution_id)
        if row is None or row.status not in _PICKUP or self.queue is None:
            return
        await self.queue.enqueue(
            Job.resume_execution,
            str(execution_id),
            job_id=resume_job_id(execution_id),
            defer_until=utcnow() + timedelta(seconds=3),
        )

    def _runtime(self, execution: Execution, snapshot: ConfigSnapshot) -> RuntimeContext:
        settings = get_settings()
        return RuntimeContext(
            execution_id=execution.id,
            workspace_id=execution.workspace_id,
            snapshot=snapshot,
            llm=LLMService(
                execution_id=execution.id,
                workspace_id=execution.workspace_id,
                snapshot=snapshot,
                bucket=self.bucket,
                concurrency=self.concurrency,
                timeout_s=settings.llm_default_timeout_s,
            ),
            tools=ToolRouter(
                execution_id=execution.id,
                workspace_id=execution.workspace_id,
                snapshot=snapshot,
                connections=self.connections,
                queue=self.queue,
            ),
            notifications=self.notifications,
            queue=self.queue,
        )

    async def _drive(self, execution: Execution, *, operator_resume: bool) -> ExecutionStatus:
        execution_id, workspace_id = execution.id, execution.workspace_id
        snapshot = ConfigSnapshot.model_validate(execution.config_snapshot)
        if execution.cancel_requested:
            await self._cancel_open_calls(execution_id)
            if execution.status == ExecutionStatus.waiting_for_timer:
                await set_execution_status(execution_id, workspace_id, ExecutionStatus.resuming, publish=False)
            await set_execution_status(
                execution_id,
                workspace_id,
                ExecutionStatus.cancelled,
                error={"code": "EXECUTION_CANCELLED", "message": "Cancelled by an operator"},
            )
            return ExecutionStatus.cancelled
        if execution.status in (ExecutionStatus.waiting_for_timer,):
            await set_execution_status(execution_id, workspace_id, ExecutionStatus.resuming)
        if execution.status != ExecutionStatus.running:
            await set_execution_status(
                execution_id, workspace_id, ExecutionStatus.running, event_payload={"worker": self.worker_id}
            )
        graph = compile_pipeline(snapshot.graph, self.checkpointer)
        rt = self._runtime(execution, snapshot)
        config: dict[str, Any] = {
            "configurable": {"thread_id": execution.thread_id, RUNTIME_KEY: rt},
            "recursion_limit": 500,
        }
        try:
            for _ in range(_MAX_PASSES):
                payload = await self._invocation(graph, config, execution, operator_resume)
                operator_resume = False
                stopped = await self._stream(graph, payload, config, execution_id)
                if stopped is not None:
                    return stopped
                status = await self._settle(graph, config, execution)
                if status is not None:
                    return status
            raise AppError("Execution did not settle after repeated resumes")
        except ExecutionCancelled as exc:
            await self._cancel_open_calls(execution_id)
            await set_execution_status(
                execution_id,
                workspace_id,
                ExecutionStatus.cancelled,
                error={"code": exc.code.value, "message": exc.message},
            )
            return ExecutionStatus.cancelled
        except Exception as exc:  # noqa: BLE001 - every failure is recorded on the execution
            err = error_dict(exc)
            log.warning("execution_failed", error=err.get("message"))
            await set_execution_status(execution_id, workspace_id, ExecutionStatus.failed, error=err)
            return ExecutionStatus.failed

    async def _invocation(self, graph: Any, config: dict[str, Any], execution: Execution, operator_resume: bool) -> Any:
        state = await graph.aget_state(config)
        if state.created_at is None:
            return {"input": execution.input or {}, "outputs": {}, "node_status": {}, "agents": {}}
        resume: dict[str, Any] = {}
        for intr in state.interrupts:
            value = intr.value if isinstance(intr.value, dict) else {}
            if await self._resolvable(value, execution.id, operator_resume):
                resume[intr.id] = {
                    "resumed_at": utcnow().isoformat(),
                    **{k: value.get(k) for k in ("kind", "approval_id")},
                }
        if resume:
            await self._mark_consumed(execution.id)
            return Command(resume=resume)
        return None

    async def _resolvable(self, value: dict[str, Any], execution_id: uuid.UUID, operator_resume: bool) -> bool:
        kind = value.get("kind")
        if kind == InterruptKind.approval.value and value.get("approval_id"):
            async with session_scope() as session:
                status = await session.scalar(
                    select(Approval.status).where(Approval.id == uuid.UUID(value["approval_id"]))
                )
            return status is not None and status != ApprovalStatus.pending
        if kind == InterruptKind.timer.value:
            async with session_scope() as session:
                timer = await session.scalar(
                    select(DurableTimer).where(
                        DurableTimer.execution_id == execution_id, DurableTimer.node_id == value.get("node_id")
                    )
                )
                if timer is not None and timer.wake_at <= utcnow():
                    timer.fired_at = timer.fired_at or utcnow()
                    return True
            return False
        if kind == InterruptKind.operator_pause.value:
            return operator_resume
        return False

    async def _mark_consumed(self, execution_id: uuid.UUID) -> None:
        async with session_scope() as session:
            await session.execute(
                sa.update(Approval)
                .where(
                    Approval.execution_id == execution_id,
                    Approval.status != ApprovalStatus.pending,
                    Approval.resumed.is_(False),
                )
                .values(resumed=True)
            )

    async def _stream(
        self, graph: Any, payload: Any, config: dict[str, Any], execution_id: uuid.UUID
    ) -> ExecutionStatus | None:
        async for _ in graph.astream(payload, config, stream_mode="checkpoints"):
            async with session_scope() as session:
                flags = (
                    await session.execute(
                        select(Execution.cancel_requested, Execution.pause_requested, Execution.workspace_id).where(
                            Execution.id == execution_id
                        )
                    )
                ).one()
            if flags.cancel_requested:
                raise ExecutionCancelled("Execution was cancelled by an operator")
            if flags.pause_requested:
                await set_execution_status(
                    execution_id, flags.workspace_id, ExecutionStatus.paused, event_payload={"reason": "operator"}
                )
                return ExecutionStatus.paused
        return None

    async def _settle(self, graph: Any, config: dict[str, Any], execution: Execution) -> ExecutionStatus | None:
        """Map the graph state after a pass to an execution status. None means run another pass."""
        state = await graph.aget_state(config)
        execution_id, workspace_id = execution.id, execution.workspace_id
        if not state.next and not state.interrupts:
            output = self._final_output(state.values, ConfigSnapshot.model_validate(execution.config_snapshot))
            await set_execution_status(execution_id, workspace_id, ExecutionStatus.completed, output=output)
            return ExecutionStatus.completed
        kinds = [i.value.get("kind") for i in state.interrupts if isinstance(i.value, dict)]
        # A decision may have arrived while this pass was running: resume immediately.
        for intr in state.interrupts:
            value = intr.value if isinstance(intr.value, dict) else {}
            if await self._resolvable(value, execution_id, False):
                return None
        if InterruptKind.approval.value in kinds:
            status = ExecutionStatus.paused_for_review
        elif InterruptKind.operator_pause.value in kinds:
            status = ExecutionStatus.paused
        elif InterruptKind.timer.value in kinds:
            status = ExecutionStatus.waiting_for_timer
        else:
            raise AppError("Execution stopped without a reason", details={"next": list(state.next)})
        pending = [i.value for i in state.interrupts if isinstance(i.value, dict)]
        await set_execution_status(execution_id, workspace_id, status, event_payload={"waiting_on": pending[:10]})
        return status

    @staticmethod
    def _final_output(values: dict[str, Any], snapshot: ConfigSnapshot) -> dict[str, Any]:
        outputs = values.get("outputs") or {}
        statuses = values.get("node_status") or {}
        ends = [n.id for n in snapshot.graph.nodes if n.type == NodeType.end and statuses.get(n.id) == "completed"]
        if len(ends) == 1:
            value = outputs.get(ends[0])
            return value if isinstance(value, dict) else {"value": value}
        return {end: outputs.get(end) for end in ends}

    async def _cancel_open_calls(self, execution_id: uuid.UUID) -> None:
        async with session_scope() as session:
            await session.execute(
                sa.update(ToolCall)
                .where(
                    ToolCall.execution_id == execution_id,
                    ToolCall.status.in_(
                        [ToolCallStatus.pending, ToolCallStatus.awaiting_approval, ToolCallStatus.approved]
                    ),
                )
                .values(status=ToolCallStatus.cancelled)
            )
            await session.execute(
                sa.update(Approval)
                .where(Approval.execution_id == execution_id, Approval.status == ApprovalStatus.pending)
                .values(status=ApprovalStatus.expired, reason="Execution cancelled")
            )
            await audit(
                session,
                event_type=AuditEventType.execution_control,
                actor=WORKER_ACTOR,
                workspace_id=None,
                entity_type="execution",
                entity_id=execution_id,
                execution_id=execution_id,
                payload={"action": "cancelled"},
            )
