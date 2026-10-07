"""Shared node machinery: branch activity, error policy and map fan-out."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from langgraph.errors import GraphBubbleUp
from langgraph.types import interrupt

from app.core.enums import ErrorCode, InterruptKind, NodeStatus
from app.core.errors import AppError, ExecutionCancelled
from app.orchestration.expressions import evaluate
from app.orchestration.runtime import RuntimeContext
from app.orchestration.state import FAILED_HANDLED, GraphState
from app.schemas.pipeline_graph import EdgeBranch, ErrorMode, PipelineEdge, PipelineGraph, PipelineNode


class NodeFailed(AppError):
    """Terminal node failure (error policy exhausted or `fail`)."""


class NodeExecutor(Protocol):
    async def run(self, node: Any, rt: RuntimeContext, state: GraphState, extra: dict[str, Any]) -> Any: ...


def error_dict(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, AppError):
        return {"code": exc.code.value, "message": exc.message, "details": exc.details, "retryable": exc.retryable}
    return {
        "code": ErrorCode.internal_error.value,
        "message": f"{exc.__class__.__name__}: {exc}"[:1000],
        "retryable": False,
    }


def edge_active(edge: PipelineEdge, graph: PipelineGraph, state: GraphState) -> bool:
    status = (state.get("node_status") or {}).get(edge.source)
    if status in (None, "skipped"):
        return False
    if status == FAILED_HANDLED:
        return edge.branch == EdgeBranch.error
    if edge.branch == EdgeBranch.error:
        return False
    if edge.branch in (EdgeBranch.true, EdgeBranch.false):
        result = ((state.get("outputs") or {}).get(edge.source) or {}).get("result")
        return (edge.branch == EdgeBranch.true) == bool(result)
    return True


def node_active(node: PipelineNode, graph: PipelineGraph, state: GraphState) -> bool:
    incoming = [e for e in graph.edges if e.target == node.id]
    if not incoming:
        return True  # trigger
    return any(edge_active(e, graph, state) for e in incoming)


async def run_with_policy(
    node: PipelineNode,
    rt: RuntimeContext,
    attempt_fn: Callable[[int], Awaitable[Any]],
) -> tuple[str, Any, dict[str, Any] | None]:
    """Run with the node's error policy. Returns (status, output, error).

    status is "completed" or FAILED_HANDLED; terminal failure raises NodeFailed. A `pause`
    policy interrupts; each failure round issues one interrupt, so re-runs stay deterministic.
    """
    policy = node.error_policy
    attempt = 0
    pause_round = 0
    while True:
        attempt += 1
        try:
            return "completed", await attempt_fn(attempt), None
        except (GraphBubbleUp, ExecutionCancelled, asyncio.CancelledError):
            raise
        except Exception as exc:
            err = error_dict(exc)
            retryable = bool(getattr(exc, "retryable", False))
            if (
                policy.mode == ErrorMode.retry
                and retryable
                and attempt < policy.max_attempts
                and await rt.consume_retry_budget()
            ):
                delay = policy.backoff_seconds * (2 ** (attempt - 1)) + random.uniform(0, policy.backoff_seconds / 2)
                await rt.node_retrying(node.id, attempt, err, delay)
                await asyncio.sleep(delay)
                continue
            outcome = policy.mode.value if policy.mode != ErrorMode.retry else policy.then
            if outcome == ErrorMode.fallback.value:
                return FAILED_HANDLED, {"error": err}, err
            if outcome == ErrorMode.pause.value:
                await rt.node_finished(node.id, node.type, node.name, NodeStatus.failed, error=err)
                interrupt(
                    {
                        "kind": InterruptKind.operator_pause.value,
                        "reason": "node_failed",
                        "node_id": node.id,
                        "round": pause_round,
                        "error": err,
                    }
                )
                pause_round += 1
                attempt = 0
                continue
            raise NodeFailed(err["message"], code=code_of(err["code"]), details={"node_id": node.id, **err}) from exc


def code_of(value: Any) -> ErrorCode:
    try:
        return ErrorCode(value)
    except ValueError:
        return ErrorCode.internal_error


async def run_mapped(
    node: PipelineNode,
    rt: RuntimeContext,
    state: GraphState,
    run_item: Callable[[Any, int], Awaitable[Any]],
) -> list[Any]:
    assert node.map is not None
    items = evaluate(node.map.over, rt.names(state))
    if items is None:
        items = []
    if not isinstance(items, list):
        raise AppError(f"map.over must evaluate to a list, got {type(items).__name__}", code=ErrorCode.expression_error)
    semaphore = asyncio.Semaphore(node.map.concurrency)

    async def one(index: int, item: Any) -> Any:
        async with semaphore:
            return await run_item(item, index)

    return list(await asyncio.gather(*(one(i, item) for i, item in enumerate(items))))
