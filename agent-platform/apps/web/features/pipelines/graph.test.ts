import { describe, expect, it } from "vitest";

import {
  canonical,
  connect,
  createNode,
  defaultsFromSchema,
  graphReducer,
  initialState,
  isDirty,
  makeEdgeId,
  makeNodeId,
  NODE_ID_PATTERN,
  removeElements,
  snake,
  suggestPosition,
  templateCompletions,
  triggerInputDefaults,
  upstreamOf,
  wouldCreateCycle,
  type Graph,
  type GraphNode,
} from "./graph";

function node(id: string, type: GraphNode["type"], x = 0, y = 0, extra: Partial<GraphNode> = {}): GraphNode {
  return { id, type, name: id, position: { x, y }, config: {}, map: null, notes: null, ...extra };
}

function base(): Graph {
  return {
    nodes: [node("trigger", "trigger", 0, 0), node("check", "condition", 260, 0), node("end", "end", 520, 0)],
    edges: [{ id: "e1", source: "trigger", target: "check", branch: null }],
  };
}

describe("ids", () => {
  it("snake-cases labels and keeps a leading letter", () => {
    expect(snake("MCP tool")).toBe("mcp_tool");
    expect(snake("  Human approval! ")).toBe("human_approval");
    expect(snake("2nd pass")).toBe("nd_pass");
    expect(snake("***")).toBe("node");
  });

  it("allocates the smallest free suffix and matches the server pattern", () => {
    expect(makeNodeId("LLM", [])).toBe("llm_1");
    expect(makeNodeId("LLM", ["llm_1", "llm_2"])).toBe("llm_3");
    const long = makeNodeId("x".repeat(200), []);
    expect(long).toMatch(NODE_ID_PATTERN);
    expect(long.length).toBeLessThanOrEqual(64);
  });

  it("makes unique edge ids including the branch", () => {
    expect(makeEdgeId("a", "b", null, [])).toBe("e_a_b");
    expect(makeEdgeId("a", "b", "true", [])).toBe("e_a_true_b");
    expect(makeEdgeId("a", "b", null, ["e_a_b"])).toBe("e_a_b_2");
  });
});

describe("defaults and creation", () => {
  it("reads defaults and seeds required fields", () => {
    const schema = {
      properties: { tool: { type: "string" }, arguments: { type: "object", default: {} }, limit: { type: "integer", default: 3 } },
      required: ["tool"],
    };
    expect(defaultsFromSchema(schema)).toEqual({ tool: "", arguments: {}, limit: 3 });
  });

  it("creates a node with a unique id and name", () => {
    const g = base();
    g.nodes.push(node("llm_1", "llm", 0, 200, { name: "LLM" }));
    const n = createNode({ type: "llm", label: "LLM", position: { x: 10.4, y: 20.6 }, graph: g });
    expect(n.id).toBe("llm_2");
    expect(n.name).toBe("LLM 2");
    expect(n.position).toEqual({ x: 10, y: 21 });
    expect(n.error_policy?.mode).toBe("retry");
  });

  it("suggests a free slot to the right of the anchor", () => {
    const g = base();
    expect(suggestPosition(g, "trigger")).toEqual({ x: 260, y: 100 }); // (260,0) is taken by `check`
    expect(suggestPosition(g)).toEqual({ x: 780, y: 0 });
    expect(suggestPosition({ nodes: [], edges: [] })).toEqual({ x: 0, y: 0 });
  });
});

describe("connect", () => {
  it("connects condition branches", () => {
    const r = connect(base(), "check", "end", "true");
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.edge).toEqual({ id: "e_check_true_end", source: "check", target: "end", branch: "true" });
  });

  it("rejects invalid connections", () => {
    const g = base();
    expect(connect(g, "check", "end", null)).toMatchObject({ ok: false });
    expect(connect(g, "trigger", "end", "true")).toMatchObject({ ok: false });
    expect(connect(g, "end", "check", null)).toMatchObject({ ok: false });
    expect(connect(g, "check", "trigger", "true")).toMatchObject({ ok: false });
    expect(connect(g, "trigger", "check", null)).toMatchObject({ ok: false, reason: "These nodes are already connected." });
    expect(connect(g, "trigger", "trigger", null)).toMatchObject({ ok: false });
  });

  it("detects cycles", () => {
    const g: Graph = {
      nodes: [node("a", "llm"), node("b", "llm"), node("c", "llm")],
      edges: [
        { id: "1", source: "a", target: "b" },
        { id: "2", source: "b", target: "c" },
      ],
    };
    expect(wouldCreateCycle(g, "c", "a")).toBe(true);
    expect(wouldCreateCycle(g, "a", "c")).toBe(false);
    expect(connect(g, "c", "a", null)).toMatchObject({ ok: false, reason: "This edge would create a cycle." });
    expect(connect(g, "a", "b", "error").ok).toBe(true);
  });
});

describe("edits", () => {
  it("removes nodes together with their edges", () => {
    const g = removeElements(base(), ["check"]);
    expect(g.nodes.map((n) => n.id)).toEqual(["trigger", "end"]);
    expect(g.edges).toEqual([]);
  });

  it("reduces add, connect, update, position and branch actions", () => {
    let s = initialState(base());
    const n = createNode({ type: "transform", label: "Transform", position: { x: 0, y: 0 }, graph: s.graph });
    s = graphReducer(s, { type: "addNode", node: n, connectFrom: "check" });
    expect(s.graph.edges.at(-1)).toMatchObject({ source: "check", target: n.id, branch: "true" });
    s = graphReducer(s, { type: "connect", source: n.id, target: "end", branch: null });
    expect(s.graph.edges).toHaveLength(3);
    s = graphReducer(s, { type: "updateNode", id: n.id, patch: { config: { mode: "expression", expression: "1" } } });
    expect(s.graph.nodes.find((x) => x.id === n.id)?.config).toEqual({ mode: "expression", expression: "1" });
    s = graphReducer(s, { type: "positions", positions: { [n.id]: { x: 5, y: 6 } } });
    expect(s.graph.nodes.find((x) => x.id === n.id)?.position).toEqual({ x: 5, y: 6 });
    const edgeId = s.graph.edges.at(-1)!.id;
    s = graphReducer(s, { type: "edgeBranch", id: edgeId, branch: "error" });
    expect(s.graph.edges.at(-1)?.branch).toBe("error");
    s = graphReducer(s, { type: "remove", edgeIds: [edgeId] });
    expect(s.graph.edges).toHaveLength(2);
  });
});

describe("dirty check", () => {
  it("ignores key order, undefined and sub-pixel jitter", () => {
    const saved = base();
    const reordered: Graph = JSON.parse(JSON.stringify(saved));
    reordered.nodes[0] = { config: {}, type: "trigger", position: { y: 0.01, x: 0 }, name: "trigger", id: "trigger", map: null, notes: null, error_policy: undefined };
    expect(canonical(saved)).toBe(canonical(reordered));
    expect(isDirty(saved, reordered)).toBe(false);
  });

  it("tracks changes against the saved graph and resets on save", () => {
    let s = initialState(base());
    expect(isDirty(s.saved, s.graph)).toBe(false);
    s = graphReducer(s, { type: "positions", positions: { end: { x: 600, y: 0 } } });
    expect(isDirty(s.saved, s.graph)).toBe(true);
    s = graphReducer(s, { type: "positions", positions: { end: { x: 520, y: 0 } } });
    expect(isDirty(s.saved, s.graph)).toBe(false);
    s = graphReducer(s, { type: "updateNode", id: "end", patch: { name: "Done" } });
    s = graphReducer(s, { type: "saved", graph: s.graph });
    expect(isDirty(s.saved, s.graph)).toBe(false);
  });

  it("restore keeps the saved graph so the editor becomes dirty", () => {
    let s = initialState(base());
    s = graphReducer(s, { type: "restore", graph: removeElements(base(), ["end"]) });
    expect(isDirty(s.saved, s.graph)).toBe(true);
  });
});

describe("derived data", () => {
  it("builds run input from trigger schema defaults", () => {
    const g = base();
    g.nodes[0]!.config = {
      input_schema: { type: "object", properties: { query: { type: "string", default: "python" }, min: { type: "integer" }, tags: { type: "array" } } },
    };
    expect(triggerInputDefaults(g)).toEqual({ query: "python", min: 0, tags: [] });
  });

  it("lists upstream nodes and template completions", () => {
    const g = base();
    g.nodes.push(node("draft", "llm", 0, 0, { map: { over: "input.items", concurrency: 2, item_name: "job" } }));
    g.edges.push({ id: "e2", source: "check", target: "draft", branch: "true" });
    expect(upstreamOf(g, "draft")).toEqual(["trigger", "check"]);
    const c = templateCompletions(g, "draft", ["my_name"]);
    expect(c).toEqual(expect.arrayContaining(["input", "nodes.trigger.output", "nodes.check.output", "job", "vars.my_name", "my_name"]));
    expect(c).not.toContain("nodes.end.output");
  });
});
