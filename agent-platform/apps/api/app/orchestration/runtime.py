"""Per-execution runtime services handed to node executors through the LangGraph config.

Nothing here is checkpointed; it is rebuilt by the runner on every start/resume.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import sqlalchemy as sa
from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from app.core.enums import EventType, NodeStatus, NodeType
from app.core.errors import ExecutionCancelled
from app.db.session import session_scope
from app.models import Execution
from app.notifications.dispatcher import NotificationDispatcher
from app.orchestration.llm_service import LLMService
from app.orchestration.read_model import node_event, summarize, upsert_node
from app.orchestration.snapshot import ConfigSnapshot
from app.orchestration.state import GraphState
from app.tools.router import ToolRouter
from app.workers.queue import JobQueue

RUNTIME_KEY = "ap_runtime"


@dataclass
class RuntimeContext:
    execution_id: uuid.UUID
    workspace_id: uuid.UUID
    snapshot: ConfigSnapshot
    llm: LLMService
    tools: ToolRouter
    notifications: NotificationDispatcher
    queue: JobQueue | None = None
    retry_budget_used: int = 0
    _started: set[str] = field(default_factory=set)

    # ---- data visible to expressions and templates -------------------------------------
    def names(self, state: GraphState, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        statuses = state.get("node_status") or {}
        nodes = {
            node_id: {"output": output, "status": statuses.get(node_id)}
            for node_id, output in (state.get("outputs") or {}).items()
        }
        names: dict[str, Any] = {
            "input": state.get("input") or {},
            "nodes": nodes,
            "vars": dict(self.snapshot.variables),
            "execution": {
                "id": str(self.execution_id),
                "pipeline": self.snapshot.pipeline_name,
                "version": self.snapshot.pipeline_version,
            },
        }
        if extra:
            names.update(extra)
        return names

    def template_context(self, state: GraphState, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """Workspace variables are also top-level names, e.g. {{ my_resume }}."""
        base = self.names(state, extra)
        return {**self.snapshot.variables, **base}

    # ---- control ----------------------------------------------------------------------------
    async def check_cancel(self) -> None:
        async with session_scope() as session:
            cancelled = await session.scalar(
                select(Execution.cancel_requested).where(Execution.id == self.execution_id)
            )
        if cancelled:
            raise ExecutionCancelled("Execution was cancelled by an operator")

    async def consume_retry_budget(self) -> bool:
        async with session_scope() as session:
            used = await session.scalar(
                sa.update(Execution)
                .where(Execution.id == self.execution_id, Execution.retries_used < self.snapshot.policy.retry_budget)
                .values(retries_used=Execution.retries_used + 1)
                .returning(Execution.retries_used)
            )
        return used is not None

    # ---- read model ---------------------------------------------------------------------------
    async def node_started(
        self, node_id: str, node_type: NodeType, name: str, attempt: int, input_value: Any = None
    ) -> None:
        await upsert_node(
            self.execution_id,
            node_id,
            node_type,
            name,
            NodeStatus.running,
            attempts=attempt,
            input_summary=summarize(input_value),
        )
        if node_id not in self._started:
            self._started.add(node_id)
            await node_event(
                self.workspace_id,
                self.execution_id,
                EventType.node_started,
                node_id,
                {"type": node_type.value, "name": name, "attempt": attempt},
            )

    async def node_finished(
        self,
        node_id: str,
        node_type: NodeType,
        name: str,
        status: NodeStatus,
        output: Any = None,
        error: dict[str, Any] | None = None,
    ) -> None:
        await upsert_node(
            self.execution_id, node_id, node_type, name, status, output_summary=summarize(output), error=error
        )
        event = {
            NodeStatus.completed: EventType.node_completed,
            NodeStatus.skipped: EventType.node_completed,
            NodeStatus.failed: EventType.node_failed,
        }.get(status)
        if event is not None:
            payload: dict[str, Any] = {"status": status.value, "type": node_type.value}
            if output is not None:
                payload["output"] = summarize(output, 1500)
            if error:
                payload["error"] = error
            await node_event(self.workspace_id, self.execution_id, event, node_id, payload)

    async def node_retrying(self, node_id: str, attempt: int, error: dict[str, Any], delay_s: float) -> None:
        await node_event(
            self.workspace_id,
            self.execution_id,
            EventType.node_retrying,
            node_id,
            {"attempt": attempt, "error": error, "delay_s": round(delay_s, 2)},
        )


def runtime_from(config: RunnableConfig) -> RuntimeContext:
    rt = (config.get("configurable") or {}).get(RUNTIME_KEY)
    if not isinstance(rt, RuntimeContext):
        raise RuntimeError("Runtime context missing from graph config")
    return rt
