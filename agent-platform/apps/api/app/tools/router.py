"""ToolRouter: the only path from an agent (or MCP Tool node) to an MCP server.

Guarantees, enforced here and nowhere else:
* every call has a `tool_calls` row keyed by a deterministic idempotency key, written
  before execution; replays reuse the recorded outcome instead of calling again;
* the policy engine runs on every call, whatever the model or pipeline says;
* approval-gated calls pause the graph with `interrupt()` and only run after a decision;
* non-read-only calls are never retried automatically; an unknown outcome goes to a human.

Interrupt determinism: LangGraph matches resume values to `interrupt()` calls by position
within a node. For each tool call we call `interrupt()` once per approval attached to that
call, in creation order, every time the node runs. Re-runs therefore always issue the same
sequence of interrupts.
"""

from __future__ import annotations

import asyncio
import json
import random
import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import sqlalchemy as sa
from langgraph.types import interrupt
from sqlalchemy import select

from app.audit.writer import audit
from app.core.enums import (
    ApprovalKind,
    ApprovalStatus,
    AuditEventType,
    ErrorCode,
    EventType,
    PolicyDecision,
    ToolCallStatus,
)
from app.core.errors import AppError, ExecutionCancelled
from app.core.ids import external_idempotency_key, idempotency_key
from app.core.logging import get_logger
from app.core.redaction import redactor
from app.core.time import utcnow
from app.db.session import session_scope
from app.events.publisher import publish_execution_event
from app.hitl.approvals import approvals_for_tool_call, create_approval
from app.llm.types import ToolDefinition
from app.mcp.connection import MCPConnection
from app.mcp.manager import MCPConnectionManager
from app.mcp.specs import build_spec
from app.mcp.types import MCPProtocolError, MCPToolTimeout, MCPTransportError, ServerSpec, ToolResult
from app.models import Approval, Execution, MCPServer, ToolCall
from app.orchestration.snapshot import ConfigSnapshot, SnapshotTool
from app.services.context import WORKER_ACTOR
from app.tools.policy import Decision, PolicyContext, ToolPolicyEngine
from app.tools.validation import argument_errors
from app.workers.queue import Job, JobQueue

log = get_logger(__name__)
_READ_ONLY_ATTEMPTS = 3
_MAX_RESULT_CHARS = 200_000


class RouteStatus(StrEnum):
    completed = "completed"
    failed = "failed"
    denied = "denied"
    rejected = "rejected"
    regenerate = "regenerate"


@dataclass
class RouteOutcome:
    status: RouteStatus
    content: str
    is_error: bool
    tool_call_id: uuid.UUID | None = None
    result: ToolResult | None = None
    edited_arguments: dict[str, Any] | None = None
    approval_id: uuid.UUID | None = None
    feedback: str | None = None
    error_code: ErrorCode | None = None
    structured: Any = None


class ToolRejected(AppError):
    code = ErrorCode.tool_not_allowed


def _json(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


class ToolRouter:
    def __init__(
        self,
        *,
        execution_id: uuid.UUID,
        workspace_id: uuid.UUID,
        snapshot: ConfigSnapshot,
        connections: MCPConnectionManager,
        queue: JobQueue | None = None,
        policy: ToolPolicyEngine | None = None,
    ) -> None:
        self.execution_id = execution_id
        self.workspace_id = workspace_id
        self.snapshot = snapshot
        self.connections = connections
        self.queue = queue
        self.policy = policy or ToolPolicyEngine()
        self._specs: dict[uuid.UUID, ServerSpec] = {}

    # ---- tool definitions for the model -------------------------------------------------
    def llm_tools(self, allowlist: list[str]) -> list[ToolDefinition]:
        out = []
        for name in allowlist:
            tool = self.snapshot.tools.get(name)
            if tool is None or not tool.is_enabled:
                continue
            out.append(ToolDefinition(name=name, description=tool.description, input_schema=tool.input_schema))
        return out

    # ---- connections ----------------------------------------------------------------------
    async def _spec(self, tool: SnapshotTool) -> ServerSpec:
        spec = self._specs.get(tool.server_id)
        if spec is None:
            async with session_scope() as session:
                server = await session.get(MCPServer, tool.server_id)
                if server is None or not server.is_active:
                    raise AppError(
                        f"MCP server {tool.server_slug} is not active",
                        code=ErrorCode.mcp_connection_failed,
                        retryable=False,
                    )
                spec = await build_spec(session, server)
            self._specs[tool.server_id] = spec
        return spec

    async def _connection(self, tool: SnapshotTool) -> MCPConnection:
        return await self.connections.get(await self._spec(tool), self.execution_id)

    async def _live_hash(self, tool: SnapshotTool) -> str:
        conn = await self._connection(tool)
        live = conn.tools.get(tool.name)
        return live.schema_hash if live is not None else "missing"

    # ---- persistence helpers --------------------------------------------------------------
    async def _row(
        self,
        key: str,
        *,
        node_id: str,
        seq: int,
        name: str,
        arguments: dict[str, Any],
        llm_tool_call_id: str | None,
        tool: SnapshotTool | None,
    ) -> ToolCall:
        async with session_scope() as session:
            row = await session.scalar(select(ToolCall).where(ToolCall.idempotency_key == key))
            if row is not None:
                return row
            row = ToolCall(
                workspace_id=self.workspace_id,
                execution_id=self.execution_id,
                node_id=node_id,
                call_seq=seq,
                llm_tool_call_id=llm_tool_call_id,
                server_id=tool.server_id if tool else None,
                tool_id=tool.tool_id if tool else None,
                tool_name=tool.name if tool else name,
                namespaced_name=name,
                arguments=arguments,
                idempotency_key=key,
                status=ToolCallStatus.pending,
                is_read_only=bool(tool and tool.safe_to_rerun),
            )
            session.add(row)
            await session.flush()
        await self._event(EventType.tool_requested, row, {"tool": name, "arguments": arguments})
        return row

    async def _update(self, row_id: uuid.UUID, **values: Any) -> ToolCall:
        async with session_scope() as session:
            await session.execute(sa.update(ToolCall).where(ToolCall.id == row_id).values(**values))
            row = await session.get(ToolCall, row_id, populate_existing=True)
            assert row is not None
            return row

    async def _reload(self, row_id: uuid.UUID) -> tuple[ToolCall, list[Approval]]:
        async with session_scope() as session:
            row = await session.get(ToolCall, row_id, populate_existing=True)
            assert row is not None
            approvals = await approvals_for_tool_call(session, row_id)
            return row, approvals

    async def _event(
        self, type: EventType, row: ToolCall, payload: dict[str, Any], approval_id: uuid.UUID | None = None
    ) -> None:
        await publish_execution_event(
            workspace_id=self.workspace_id,
            execution_id=self.execution_id,
            type=type,
            node_id=row.node_id,
            tool_call_id=row.id,
            approval_id=approval_id,
            payload=payload,
        )

    async def _cancel_requested(self) -> bool:
        async with session_scope() as session:
            return bool(
                await session.scalar(select(Execution.cancel_requested).where(Execution.id == self.execution_id))
            )

    # ---- main entry ---------------------------------------------------------------------------
    async def route(
        self,
        *,
        node_id: str,
        call_seq: int,
        name: str,
        arguments: dict[str, Any],
        llm_tool_call_id: str | None = None,
        allowlist: list[str] | None = None,
        in_map: bool = False,
        supersedes: uuid.UUID | None = None,
        can_regenerate: bool = False,
        context_summary: str | None = None,
    ) -> RouteOutcome:
        tool = self.snapshot.tools.get(name)
        key = idempotency_key(self.execution_id, node_id, call_seq)
        row = await self._row(
            key,
            node_id=node_id,
            seq=call_seq,
            name=name,
            arguments=arguments,
            llm_tool_call_id=llm_tool_call_id,
            tool=tool,
        )
        row, approvals = await self._reload(row.id)

        if row.status == ToolCallStatus.completed:
            return self._completed_outcome(row)

        if row.status == ToolCallStatus.pending and not approvals:
            early = await self._evaluate_new(
                row, tool, name, arguments, allowlist, in_map, supersedes, can_regenerate, context_summary
            )
            if early is not None:
                return early
            row, approvals = await self._reload(row.id)

        if (
            row.status in (ToolCallStatus.outcome_unknown, ToolCallStatus.executing)
            and tool is not None
            and not tool.safe_to_rerun
        ):
            await self._ensure_outcome_approval(row, approvals)
            row, approvals = await self._reload(row.id)

        # Deterministic interrupt sequence: one per attached approval, in creation order.
        for approval in approvals:
            interrupt({"kind": "approval", "approval_id": str(approval.id), "tool": name, "tool_call_id": str(row.id)})
        row, approvals = await self._reload(row.id)
        return await self._apply_decisions(row, approvals, tool, name)

    # ---- first evaluation -------------------------------------------------------------------
    async def _evaluate_new(
        self,
        row: ToolCall,
        tool: SnapshotTool | None,
        name: str,
        arguments: dict[str, Any],
        allowlist: list[str] | None,
        in_map: bool,
        supersedes: uuid.UUID | None,
        can_regenerate: bool,
        context_summary: str | None,
    ) -> RouteOutcome | None:
        if tool is not None:
            errors = argument_errors(tool.input_schema, arguments)
            if errors:
                row = await self._update(
                    row.id,
                    status=ToolCallStatus.failed,
                    error={
                        "code": ErrorCode.tool_arguments_invalid.value,
                        "message": "Arguments do not match the tool schema",
                        "fields": errors,
                        "retryable": False,
                    },
                )
                await self._event(EventType.tool_failed, row, {"tool": name, "error": row.error})
                return RouteOutcome(
                    RouteStatus.failed,
                    _json({"error": "invalid_arguments", "fields": errors}),
                    True,
                    row.id,
                    error_code=ErrorCode.tool_arguments_invalid,
                )
        live_hash: str | None = None
        if tool is not None and tool.is_enabled and (allowlist is None or name in allowlist):
            live_hash = await self._live_hash(tool)
        decision = self.policy.evaluate(
            name,
            tool,
            PolicyContext(
                execution_id=self.execution_id,
                workspace_id=self.workspace_id,
                node_id=row.node_id,
                allowlist=frozenset(allowlist) if allowlist is not None else None,
                started_by_role=self.snapshot.policy.started_by_role,
                live_schema_hash=live_hash,
                arguments=arguments,
            ),
        )
        if decision.decision == PolicyDecision.deny:
            return await self._deny(row, name, decision)
        if decision.decision == PolicyDecision.allow:
            await self._update(row.id, policy_decision=decision.to_dict())
            return await self._execute(row.id, tool, arguments)  # type: ignore[arg-type]
        if in_map:
            await self._update(
                row.id,
                status=ToolCallStatus.failed,
                policy_decision=decision.to_dict(),
                error={
                    "code": ErrorCode.approval_not_allowed_in_map.value,
                    "retryable": False,
                    "message": "Approval-gated tools cannot run inside a mapped node",
                },
            )
            raise AppError(
                "Approval-gated tools cannot run inside a mapped (fan-out) node",
                code=ErrorCode.approval_not_allowed_in_map,
            )
        assert tool is not None
        async with session_scope() as session:
            approval = await create_approval(
                session,
                workspace_id=self.workspace_id,
                execution_id=self.execution_id,
                node_id=row.node_id,
                kind=ApprovalKind.tool_call,
                tool_call_id=row.id,
                title=f"{tool.server_slug} · {tool.name}",
                summary=context_summary,
                risk_level=decision.risk_level.value,
                reasons=decision.reasons,
                original_arguments=arguments,
                payload={
                    "tool": name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "can_regenerate": can_regenerate,
                    "is_destructive": tool.is_destructive,
                },
                expires_in_minutes=self.snapshot.policy.approval_expiry_minutes,
                supersedes=supersedes,
            )
            await session.execute(
                sa.update(ToolCall)
                .where(ToolCall.id == row.id)
                .values(status=ToolCallStatus.awaiting_approval, policy_decision=decision.to_dict())
            )
        await self._event(
            EventType.tool_awaiting_approval, row, {"tool": name, "reasons": decision.reasons}, approval.id
        )
        await publish_execution_event(
            workspace_id=self.workspace_id,
            execution_id=self.execution_id,
            type=EventType.approval_created,
            node_id=row.node_id,
            approval_id=approval.id,
            tool_call_id=row.id,
            payload={"title": approval.title, "risk_level": approval.risk_level, "tool": name},
        )
        if self.queue is not None:
            await self.queue.enqueue(Job.send_notification, str(approval.id), job_id=f"notify:{approval.id}")
        return None

    async def _deny(self, row: ToolCall, name: str, decision: Decision) -> RouteOutcome:
        code = decision.code or ErrorCode.tool_not_allowed
        row = await self._update(
            row.id,
            status=ToolCallStatus.rejected,
            policy_decision=decision.to_dict(),
            error={"code": code.value, "message": decision.reasons[0], "retryable": False},
        )
        async with session_scope() as session:
            await audit(
                session,
                event_type=AuditEventType.tool_denied,
                actor=WORKER_ACTOR,
                workspace_id=self.workspace_id,
                entity_type="tool_call",
                entity_id=row.id,
                execution_id=self.execution_id,
                payload={"tool": name, "reasons": decision.reasons},
            )
        await self._event(EventType.tool_failed, row, {"tool": name, "error": row.error})
        return RouteOutcome(
            RouteStatus.denied,
            _json({"error": code.value, "message": decision.reasons[0]}),
            True,
            row.id,
            error_code=code,
        )

    async def _ensure_outcome_approval(self, row: ToolCall, approvals: list[Approval]) -> None:
        if row.status == ToolCallStatus.executing:
            row = await self._update(row.id, status=ToolCallStatus.outcome_unknown)
        attempt = row.attempt
        if any(
            a.kind == ApprovalKind.outcome_unknown and (a.payload or {}).get("attempt") == attempt for a in approvals
        ):
            return
        async with session_scope() as session:
            approval = await create_approval(
                session,
                workspace_id=self.workspace_id,
                execution_id=self.execution_id,
                node_id=row.node_id,
                kind=ApprovalKind.outcome_unknown,
                tool_call_id=row.id,
                title=f"Outcome unknown · {row.namespaced_name}",
                summary="The worker stopped while this call was running. It may or may not have taken effect. "
                "Check the target system, then record what happened.",
                risk_level="high",
                reasons=["Execution was interrupted during a non-read-only tool call"],
                original_arguments=row.arguments,
                payload={"tool": row.namespaced_name, "attempt": attempt},
            )
        await publish_execution_event(
            workspace_id=self.workspace_id,
            execution_id=self.execution_id,
            type=EventType.approval_created,
            node_id=row.node_id,
            approval_id=approval.id,
            tool_call_id=row.id,
            payload={"title": approval.title, "kind": "outcome_unknown", "tool": row.namespaced_name},
        )
        if self.queue is not None:
            await self.queue.enqueue(Job.send_notification, str(approval.id), job_id=f"notify:{approval.id}")

    # ---- decisions ----------------------------------------------------------------------------
    async def _apply_decisions(
        self, row: ToolCall, approvals: list[Approval], tool: SnapshotTool | None, name: str
    ) -> RouteOutcome:
        if row.status == ToolCallStatus.completed:
            return self._completed_outcome(row)
        if row.status == ToolCallStatus.rejected and not approvals:
            err = row.error or {}
            return RouteOutcome(
                RouteStatus.denied, _json({"error": err.get("code"), "message": err.get("message")}), True, row.id
            )
        gate = next((a for a in reversed(approvals) if a.kind == ApprovalKind.tool_call), None)
        outcome_review = next(
            (
                a
                for a in reversed(approvals)
                if a.kind == ApprovalKind.outcome_unknown and (a.payload or {}).get("attempt") == row.attempt
            ),
            None,
        )
        if gate is not None and gate.status == ApprovalStatus.rejected:
            return RouteOutcome(
                RouteStatus.rejected,
                _json(
                    {
                        "rejected": True,
                        "by": "human reviewer",
                        "reason": gate.reason or "No reason given",
                        "instruction": "Do not retry this exact action. Adjust or finish.",
                    }
                ),
                True,
                row.id,
                approval_id=gate.id,
            )
        if gate is not None and gate.status in (ApprovalStatus.superseded, ApprovalStatus.expired):
            if gate.status == ApprovalStatus.expired:
                return RouteOutcome(
                    RouteStatus.rejected,
                    _json({"rejected": True, "reason": "Approval expired"}),
                    True,
                    row.id,
                    approval_id=gate.id,
                )
            return RouteOutcome(
                RouteStatus.regenerate,
                _json(
                    {
                        "not_executed": True,
                        "reviewer_requested_new_proposal": True,
                        "feedback": gate.feedback or "Propose a better action.",
                    }
                ),
                True,
                row.id,
                approval_id=gate.id,
                feedback=gate.feedback,
            )
        if outcome_review is not None:
            action = (outcome_review.resolution or {}).get("action")
            if action == "mark_succeeded":
                result = (outcome_review.resolution or {}).get("result")
                row = await self._update(
                    row.id,
                    status=ToolCallStatus.completed,
                    finished_at=utcnow(),
                    result={
                        "success": True,
                        "content": _json(result) if result is not None else "Marked as succeeded by a reviewer",
                        "structured_content": result,
                        "metadata": {"resolved_by_human": True},
                    },
                )
                return self._completed_outcome(row)
            if action == "mark_failed":
                row = await self._update(
                    row.id,
                    status=ToolCallStatus.failed,
                    finished_at=utcnow(),
                    error={
                        "code": ErrorCode.mcp_tool_error.value,
                        "message": "Marked as failed by a reviewer",
                        "retryable": False,
                    },
                )
                return RouteOutcome(
                    RouteStatus.failed,
                    _json({"error": "failed", "message": "Marked failed by a reviewer"}),
                    True,
                    row.id,
                )
            # rerun: explicit human confirmation, execute once more below
        if row.status in (ToolCallStatus.failed, ToolCallStatus.timeout):
            err = row.error or {}
            if row.is_read_only and err.get("retryable") and tool is not None:
                return await self._execute(row.id, tool, row.arguments)
            return RouteOutcome(
                RouteStatus.failed,
                _json({"error": err.get("code"), "message": err.get("message")}),
                True,
                row.id,
                error_code=_code(err.get("code")),
            )
        if tool is None:
            return RouteOutcome(RouteStatus.denied, _json({"error": "tool_unavailable"}), True, row.id)
        arguments = row.arguments
        edited = None
        if gate is not None and gate.edited_arguments is not None:
            edited = gate.edited_arguments
            arguments = edited
            if row.arguments != edited:
                await self._update(row.id, arguments=edited)
        outcome = await self._execute(row.id, tool, arguments)
        outcome.edited_arguments = edited
        outcome.approval_id = gate.id if gate else None
        return outcome

    def _completed_outcome(self, row: ToolCall) -> RouteOutcome:
        result = row.result or {}
        content = result.get("content") or _json(result.get("structured_content"))
        return RouteOutcome(
            RouteStatus.completed,
            content,
            False,
            row.id,
            result=ToolResult(
                success=True,
                tool_name=row.tool_name,
                content=content,
                structured_content=result.get("structured_content"),
                metadata=result.get("metadata") or {},
                duration_ms=row.duration_ms or 0,
            ),
            structured=result.get("structured_content")
            if result.get("structured_content") is not None
            else _maybe_json(content),
        )

    # ---- execution ----------------------------------------------------------------------------
    async def _execute(self, row_id: uuid.UUID, tool: SnapshotTool, arguments: dict[str, Any]) -> RouteOutcome:
        if await self._cancel_requested():
            await self._update(row_id, status=ToolCallStatus.cancelled)
            raise ExecutionCancelled("Execution was cancelled")
        live_hash = await self._live_hash(tool)
        if live_hash != tool.schema_hash:
            row = await self._update(
                row_id,
                status=ToolCallStatus.failed,
                error={
                    "code": ErrorCode.tool_schema_changed.value,
                    "retryable": False,
                    "message": "The tool's live schema no longer matches this execution's snapshot",
                },
            )
            await self._event(EventType.tool_failed, row, {"tool": tool.namespaced_name, "error": row.error})
            return RouteOutcome(
                RouteStatus.failed,
                _json({"error": ErrorCode.tool_schema_changed.value}),
                True,
                row.id,
                error_code=ErrorCode.tool_schema_changed,
            )
        attempts = _READ_ONLY_ATTEMPTS if tool.safe_to_rerun else 1
        last_error: AppError | None = None
        for attempt in range(1, attempts + 1):
            row = await self._update(
                row_id, status=ToolCallStatus.executing, attempt=ToolCall.attempt + 1, started_at=utcnow(), error=None
            )
            key = row.idempotency_key
            await self._event(EventType.tool_executing, row, {"tool": tool.namespaced_name, "attempt": row.attempt})
            try:
                conn = await self._connection(tool)
                result = await conn.call_tool(
                    tool.name, arguments, meta={"idempotency_key": external_idempotency_key(key)}
                )
            except asyncio.CancelledError:
                await self._update(
                    row_id, status=ToolCallStatus.pending if tool.safe_to_rerun else ToolCallStatus.outcome_unknown
                )
                raise
            except (MCPTransportError, MCPToolTimeout) as exc:
                last_error = exc
                if tool.safe_to_rerun:
                    status = ToolCallStatus.timeout if isinstance(exc, MCPToolTimeout) else ToolCallStatus.failed
                    await self._update(
                        row_id, status=status, error={"code": exc.code.value, "message": exc.message, "retryable": True}
                    )
                    if attempt < attempts:
                        await asyncio.sleep(min(8.0, 0.5 * 2**attempt) + random.uniform(0, 0.3))
                        continue
                    row = await self._update(row_id, finished_at=utcnow())
                    await self._event(EventType.tool_failed, row, {"tool": tool.namespaced_name, "error": row.error})
                    return RouteOutcome(
                        RouteStatus.failed,
                        _json({"error": exc.code.value, "message": exc.message}),
                        True,
                        row_id,
                        error_code=exc.code,
                    )
                # Never retry a call that may have taken effect.
                row = await self._update(
                    row_id,
                    status=ToolCallStatus.outcome_unknown,
                    error={"code": exc.code.value, "message": exc.message, "retryable": False},
                )
                await self._event(
                    EventType.tool_failed,
                    row,
                    {"tool": tool.namespaced_name, "error": row.error, "outcome_unknown": True},
                )
                row, approvals = await self._reload(row_id)
                await self._ensure_outcome_approval(row, approvals)
                _, approvals = await self._reload(row_id)
                interrupt(
                    {
                        "kind": "approval",
                        "approval_id": str(approvals[-1].id),
                        "tool": tool.namespaced_name,
                        "tool_call_id": str(row_id),
                    }
                )
                row, approvals = await self._reload(row_id)
                return await self._apply_decisions(row, approvals, tool, tool.namespaced_name)
            except MCPProtocolError as exc:
                row = await self._update(
                    row_id,
                    status=ToolCallStatus.failed,
                    finished_at=utcnow(),
                    error={"code": exc.code.value, "message": exc.message, "retryable": False},
                )
                await self._event(EventType.tool_failed, row, {"tool": tool.namespaced_name, "error": row.error})
                return RouteOutcome(
                    RouteStatus.failed,
                    _json({"error": "protocol_error", "message": exc.message}),
                    True,
                    row_id,
                    error_code=exc.code,
                )
            return await self._record_result(row_id, tool, arguments, result)
        assert last_error is not None
        raise last_error

    async def _record_result(
        self, row_id: uuid.UUID, tool: SnapshotTool, arguments: dict[str, Any], result: ToolResult
    ) -> RouteOutcome:
        content = result.content[:_MAX_RESULT_CHARS]
        stored = {
            "success": result.success,
            "content": content,
            "structured_content": result.structured_content,
            "metadata": result.metadata,
        }
        if result.success:
            row = await self._update(
                row_id,
                status=ToolCallStatus.completed,
                result=stored,
                duration_ms=result.duration_ms,
                finished_at=utcnow(),
            )
        else:
            row = await self._update(
                row_id,
                status=ToolCallStatus.failed,
                result=stored,
                duration_ms=result.duration_ms,
                finished_at=utcnow(),
                error={
                    "code": ErrorCode.mcp_tool_error.value,
                    "message": (result.error or {}).get("message", "Tool reported an error"),
                    "retryable": False,
                },
            )
        async with session_scope() as session:
            await audit(
                session,
                event_type=AuditEventType.tool_executed,
                actor=WORKER_ACTOR,
                workspace_id=self.workspace_id,
                entity_type="tool_call",
                entity_id=row_id,
                execution_id=self.execution_id,
                payload={
                    "tool": tool.namespaced_name,
                    "arguments": arguments,
                    "success": result.success,
                    "duration_ms": result.duration_ms,
                    "attempt": row.attempt,
                },
            )
        await self._event(
            EventType.tool_completed if result.success else EventType.tool_failed,
            row,
            {
                "tool": tool.namespaced_name,
                "duration_ms": result.duration_ms,
                "preview": redactor.redact_text(content[:500]),
            },
        )
        if result.success:
            return self._completed_outcome(row)
        return RouteOutcome(
            RouteStatus.failed,
            _json({"error": "tool_error", "message": content[:2000]}),
            True,
            row_id,
            result=result,
            error_code=ErrorCode.mcp_tool_error,
        )


def _code(value: Any) -> ErrorCode | None:
    try:
        return ErrorCode(value)
    except ValueError:
        return None


def _maybe_json(text: str) -> Any:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return text
