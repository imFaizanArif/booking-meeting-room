"""Static validation of a pipeline graph before it is saved or compiled."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.core.enums import NodeType
from app.orchestration.expressions import check_syntax
from app.prompts.render import TemplateError, referenced_variables
from app.schemas.pipeline_graph import (
    MAPPABLE,
    AgentNode,
    ConditionNode,
    EdgeBranch,
    ErrorMode,
    LLMNode,
    MCPToolNode,
    PipelineGraph,
)


@dataclass
class GraphIssue:
    message: str
    node_id: str | None = None
    edge_id: str | None = None
    severity: str = "error"


@dataclass
class ValidationResult:
    issues: list[GraphIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    def error(self, message: str, node_id: str | None = None, edge_id: str | None = None) -> None:
        self.issues.append(GraphIssue(message, node_id, edge_id))

    def warn(self, message: str, node_id: str | None = None) -> None:
        self.issues.append(GraphIssue(message, node_id, None, "warning"))


def parse_graph(raw: dict[str, Any]) -> tuple[PipelineGraph | None, ValidationResult]:
    result = ValidationResult()
    try:
        return PipelineGraph.model_validate(raw), result
    except ValidationError as exc:
        for err in exc.errors()[:50]:
            loc = ".".join(str(p) for p in err["loc"])
            node_id = None
            if len(err["loc"]) > 1 and err["loc"][0] == "nodes" and isinstance(err["loc"][1], int):
                nodes = raw.get("nodes") or []
                idx = err["loc"][1]
                if idx < len(nodes) and isinstance(nodes[idx], dict):
                    node_id = nodes[idx].get("id")
            result.error(f"{loc}: {err['msg']}", node_id=node_id)
        return None, result


def topological_order(graph: PipelineGraph) -> list[str] | None:
    indeg: dict[str, int] = {n.id: 0 for n in graph.nodes}
    out: dict[str, list[str]] = defaultdict(list)
    for e in graph.edges:
        if e.source in indeg and e.target in indeg:
            indeg[e.target] += 1
            out[e.source].append(e.target)
    queue = deque(sorted(n for n, d in indeg.items() if d == 0))
    order: list[str] = []
    while queue:
        n = queue.popleft()
        order.append(n)
        for t in out[n]:
            indeg[t] -= 1
            if indeg[t] == 0:
                queue.append(t)
    return order if len(order) == len(indeg) else None


def validate_graph(graph: PipelineGraph, *, known_tools: set[str] | None = None) -> ValidationResult:
    result = ValidationResult()
    ids = [n.id for n in graph.nodes]
    if len(ids) != len(set(ids)):
        result.error("Node ids must be unique")
    id_set = set(ids)
    triggers = [n for n in graph.nodes if n.type == NodeType.trigger]
    ends = [n for n in graph.nodes if n.type == NodeType.end]
    if len(triggers) != 1:
        result.error("A pipeline needs exactly one Trigger node")
    if not ends:
        result.error("A pipeline needs at least one End node")

    edge_ids: set[str] = set()
    incoming: dict[str, list[str]] = defaultdict(list)
    outgoing: dict[str, list[Any]] = defaultdict(list)
    for e in graph.edges:
        if e.id in edge_ids:
            result.error("Edge ids must be unique", edge_id=e.id)
        edge_ids.add(e.id)
        if e.source not in id_set or e.target not in id_set:
            result.error("Edge points to a missing node", edge_id=e.id)
            continue
        if e.source == e.target:
            result.error("Edge cannot connect a node to itself", edge_id=e.id)
        source = graph.node(e.source)
        if e.branch in (EdgeBranch.true, EdgeBranch.false) and source.type != NodeType.condition:
            result.error("true/false branches can only leave a Condition node", edge_id=e.id)
        if e.branch == EdgeBranch.error and source.error_policy.mode != ErrorMode.fallback \
                and source.error_policy.then != "fallback":
            result.warn("Error edge is only used when the node's error policy falls back", node_id=e.source)
        incoming[e.target].append(e.source)
        outgoing[e.source].append(e)

    if topological_order(graph) is None:
        result.error("The pipeline graph contains a cycle; pipelines must be acyclic")

    for node in graph.nodes:
        if node.type == NodeType.trigger and incoming[node.id]:
            result.error("Trigger cannot have incoming edges", node_id=node.id)
        if node.type != NodeType.trigger and not incoming[node.id]:
            result.error("Node is not connected to the trigger", node_id=node.id)
        if node.type == NodeType.end and outgoing[node.id]:
            result.error("End cannot have outgoing edges", node_id=node.id)
        if node.type not in (NodeType.end,) and not outgoing[node.id]:
            result.warn("Node has no outgoing edge; its output is unused", node_id=node.id)
        if node.map is not None:
            if node.type not in MAPPABLE:
                result.error(f"{node.type.value} nodes cannot be mapped (fan-out)", node_id=node.id)
            elif (msg := check_syntax(node.map.over)):
                result.error(f"map.over: {msg}", node_id=node.id)
        if isinstance(node, ConditionNode):
            if (msg := check_syntax(node.config.expression)):
                result.error(f"expression: {msg}", node_id=node.id)
            branches = {e.branch for e in outgoing[node.id]}
            if not branches & {EdgeBranch.true, EdgeBranch.false}:
                result.error("Condition needs at least one true or false edge", node_id=node.id)
        if isinstance(node, (LLMNode, AgentNode)):
            for label, source in (("user_prompt", node.config.user_prompt),
                                  ("system_prompt", node.config.system_prompt.inline or "")):
                try:
                    referenced_variables(source)
                except TemplateError as exc:
                    result.error(f"{label}: {exc.message}", node_id=node.id)
        if isinstance(node, AgentNode):
            if not node.config.tool_allowlist:
                result.warn("Agent has no tools in its allow-list", node_id=node.id)
            if known_tools is not None:
                for name in node.config.tool_allowlist:
                    if name not in known_tools:
                        result.error(f"Unknown tool {name}", node_id=node.id)
        if isinstance(node, MCPToolNode) and known_tools is not None and node.config.tool not in known_tools:
            result.error(f"Unknown tool {node.config.tool}", node_id=node.id)
    return result
