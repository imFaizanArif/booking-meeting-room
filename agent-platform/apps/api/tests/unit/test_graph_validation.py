"""Static pipeline validation."""

from __future__ import annotations

from typing import Any

import pytest

from app.core.errors import ValidationFailed
from app.orchestration.compiler import compile_pipeline
from app.orchestration.validation import parse_graph, topological_order, validate_graph
from app.schemas.pipeline_graph import PipelineGraph


def node(node_id: str, type_: str, **extra: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "condition": {"expression": "True"}, "mcp_tool": {"tool": "s__t"}, "end": {"output": "=nodes"},
    }.get(type_, {})
    return {"id": node_id, "type": type_, "name": node_id, "config": extra.pop("config", config), **extra}


def edge(source: str, target: str, branch: str | None = None) -> dict[str, Any]:
    return {"id": f"{source}_{target}", "source": source, "target": target, "branch": branch}


def graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> PipelineGraph:
    return PipelineGraph.model_validate({"nodes": nodes, "edges": edges})


def errors(g: PipelineGraph, **kw: Any) -> list[str]:
    return [i.message for i in validate_graph(g, **kw).issues if i.severity == "error"]


LINEAR = graph([node("trigger", "trigger"), node("step", "transform"), node("end", "end")],
               [edge("trigger", "step"), edge("step", "end")])


def test_valid_graph_compiles() -> None:
    assert validate_graph(LINEAR).ok
    assert topological_order(LINEAR) == ["trigger", "step", "end"]
    assert compile_pipeline(LINEAR, None) is not None


def test_cycle_rejected() -> None:
    g = graph([node("trigger", "trigger"), node("a", "transform"), node("b", "transform"), node("end", "end")],
              [edge("trigger", "a"), edge("a", "b"), edge("b", "a"), edge("b", "end")])
    assert topological_order(g) is None
    assert any("cycle" in m for m in errors(g))
    with pytest.raises(ValidationFailed) as info:
        compile_pipeline(g, None)
    assert any("cycle" in i["message"] for i in info.value.details["issues"])


def test_missing_trigger_and_end() -> None:
    g = graph([node("step", "transform")], [])
    messages = errors(g)
    assert "A pipeline needs exactly one Trigger node" in messages
    assert "A pipeline needs at least one End node" in messages
    two = graph([node("t1", "trigger"), node("t2", "trigger"), node("end", "end")],
                [edge("t1", "end"), edge("t2", "end")])
    assert "A pipeline needs exactly one Trigger node" in errors(two)


@pytest.mark.parametrize("type_", ["agent", "human_approval", "condition", "delay"])
def test_map_rejected_on_non_mappable_nodes(type_: str) -> None:
    g = graph([node("trigger", "trigger"), node("x", type_, map={"over": "input.items"}), node("end", "end")],
              [edge("trigger", "x", None), edge("x", "end", "true" if type_ == "condition" else None)])
    assert f"{type_} nodes cannot be mapped (fan-out)" in errors(g)


def test_map_allowed_on_llm_but_syntax_checked() -> None:
    ok = graph([node("trigger", "trigger"), node("x", "llm", map={"over": "input.items"}), node("end", "end")],
               [edge("trigger", "x"), edge("x", "end")])
    assert errors(ok) == []
    bad = graph([node("trigger", "trigger"), node("x", "llm", map={"over": "len(input"}), node("end", "end")],
                [edge("trigger", "x"), edge("x", "end")])
    assert any(m.startswith("map.over: Syntax error") for m in errors(bad))


def test_structural_rules() -> None:
    g = graph(
        [node("trigger", "trigger"), node("c", "condition"), node("loose", "transform"), node("end", "end"),
         node("t2", "transform")],
        [edge("trigger", "c"), edge("c", "end", "true"), edge("end", "t2"), edge("trigger", "t2", "true"),
         edge("t2", "ghost")],
    )
    messages = errors(g)
    assert "Node is not connected to the trigger" in messages  # loose
    assert "End cannot have outgoing edges" in messages
    assert "true/false branches can only leave a Condition node" in messages
    assert "Edge points to a missing node" in messages


def test_condition_needs_branch_and_unknown_tools_flagged() -> None:
    g = graph([node("trigger", "trigger"), node("c", "condition"), node("call", "mcp_tool"), node("end", "end")],
              [edge("trigger", "c"), edge("c", "call"), edge("call", "end")])
    assert "Condition needs at least one true or false edge" in errors(g)
    assert "Unknown tool s__t" in errors(g, known_tools={"other__tool"})
    assert "Unknown tool s__t" not in errors(g, known_tools={"s__t"})


def test_parse_graph_reports_node_ids() -> None:
    parsed, result = parse_graph({"nodes": [{"id": "Bad Id", "type": "trigger", "name": "x"},
                                            {"id": "ok", "type": "mcp_tool", "name": "x", "config": {}}],
                                  "edges": []})
    assert parsed is None and not result.ok
    assert {"Bad Id", "ok"} <= {i.node_id for i in result.issues}
    template = graph([node("trigger", "trigger"), node("x", "llm", config={"user_prompt": "{% if %}"}),
                      node("end", "end")], [edge("trigger", "x"), edge("x", "end")])
    assert any(m.startswith("user_prompt: Template syntax error") for m in errors(template))
