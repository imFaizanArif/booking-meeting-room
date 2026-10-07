"""Compile an immutable pipeline version into a LangGraph StateGraph.

* every pipeline node -> one LangGraph node (Agent -> compiled subgraph);
* every pipeline edge -> one edge; nodes with several incoming edges use a waiting edge
  (`add_edge([a, b], c)`) so joins run once, after all inputs;
* branch selection is data: each node checks whether any incoming edge is active (condition
  result, error route, upstream skipped) and records `skipped` otherwise.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.core.enums import NodeStatus, NodeType
from app.core.errors import ValidationFailed
from app.orchestration.nodes.agent import build_agent_subgraph
from app.orchestration.nodes.base import NodeExecutor, node_active, run_mapped, run_with_policy
from app.orchestration.nodes.llm_tool import LLMExecutor, MCPToolExecutor
from app.orchestration.nodes.simple import (
    ConditionExecutor,
    DelayExecutor,
    EndExecutor,
    HumanApprovalExecutor,
    NotificationExecutor,
    TransformExecutor,
    TriggerExecutor,
)
from app.orchestration.runtime import runtime_from
from app.orchestration.state import FAILED_HANDLED, GraphState
from app.orchestration.validation import validate_graph
from app.schemas.pipeline_graph import AgentNode, PipelineGraph, PipelineNode

EXECUTORS: dict[NodeType, NodeExecutor] = {
    NodeType.trigger: TriggerExecutor(),
    NodeType.llm: LLMExecutor(),
    NodeType.mcp_tool: MCPToolExecutor(),
    NodeType.condition: ConditionExecutor(),
    NodeType.transform: TransformExecutor(),
    NodeType.human_approval: HumanApprovalExecutor(),
    NodeType.notification: NotificationExecutor(),
    NodeType.delay: DelayExecutor(),
    NodeType.end: EndExecutor(),
}


def make_node_fn(node: PipelineNode, graph: PipelineGraph) -> Any:
    executor = EXECUTORS[node.type]

    async def run(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
        rt = runtime_from(config)
        if not node_active(node, graph, state):
            await rt.node_finished(node.id, node.type, node.name, NodeStatus.skipped)
            return {"node_status": {node.id: NodeStatus.skipped.value}}
        await rt.check_cancel()

        async def attempt(n: int) -> Any:
            await rt.node_started(node.id, node.type, node.name, n)
            if node.map is not None:
                item_name = node.map.item_name

                async def run_item(item: Any, index: int) -> Any:
                    return await executor.run(node, rt, state, {item_name: item, "index": index, "__index__": index})

                return await run_mapped(node, rt, state, run_item)
            return await executor.run(node, rt, state, {})

        status, output, error = await run_with_policy(node, rt, attempt)
        if status == FAILED_HANDLED:
            await rt.node_finished(node.id, node.type, node.name, NodeStatus.failed, output=output, error=error)
            return {"outputs": {node.id: output}, "node_status": {node.id: FAILED_HANDLED}}
        await rt.node_finished(node.id, node.type, node.name, NodeStatus.completed, output=output)
        return {"outputs": {node.id: output}, "node_status": {node.id: NodeStatus.completed.value}}

    run.__name__ = f"node_{node.id}"
    return run


def compile_pipeline(graph: PipelineGraph, checkpointer: BaseCheckpointSaver[Any] | None) -> CompiledStateGraph:
    result = validate_graph(graph)
    if not result.ok:
        raise ValidationFailed(
            "Pipeline graph is invalid",
            details={"issues": [i.__dict__ for i in result.issues if i.severity == "error"]},
        )
    builder = StateGraph(GraphState)
    for node in graph.nodes:
        if isinstance(node, AgentNode):
            builder.add_node(node.id, build_agent_subgraph(node, graph))
        else:
            builder.add_node(node.id, make_node_fn(node, graph))

    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in graph.edges:
        if edge.source not in incoming[edge.target]:
            incoming[edge.target].append(edge.source)
            outgoing[edge.source].append(edge.target)
    for node in graph.nodes:
        sources = incoming[node.id]
        if node.type == NodeType.trigger:
            builder.add_edge(START, node.id)
        elif len(sources) == 1:
            builder.add_edge(sources[0], node.id)
        elif sources:
            builder.add_edge(sources, node.id)
        if not outgoing[node.id]:
            builder.add_edge(node.id, END)
    return builder.compile(checkpointer=checkpointer)
