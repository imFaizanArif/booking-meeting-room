/**
 * Pure graph-state helpers for the pipeline builder.
 *
 * The pipeline graph JSON (as stored in a pipeline version) is the single source of truth
 * in the builder. React Flow nodes/edges are derived from it; every edit goes through
 * `graphReducer`. Nothing in this file touches React.
 */

import type { Schemas } from "@/lib/api/client";

export type NodeType = Schemas["NodeType"];
export type Branch = "true" | "false" | "error";
export type ErrorMode = "fail" | "retry" | "fallback" | "pause";

export interface Position {
  x: number;
  y: number;
}

export interface MapSpec {
  over: string;
  concurrency: number;
  item_name: string;
}

export interface ErrorPolicy {
  mode: ErrorMode;
  max_attempts: number;
  backoff_seconds: number;
  then: "fail" | "fallback" | "pause";
}

export interface GraphNode {
  id: string;
  type: NodeType;
  name: string;
  position: Position;
  config: Record<string, unknown>;
  map?: MapSpec | null;
  error_policy?: ErrorPolicy;
  notes?: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  branch?: Branch | null;
}

export interface Graph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export const NODE_ID_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;
export const MAPPABLE: ReadonlySet<NodeType> = new Set<NodeType>(["llm", "mcp_tool", "transform", "notification"]);
export const DEFAULT_ERROR_POLICY: ErrorPolicy = { mode: "retry", max_attempts: 3, backoff_seconds: 1, then: "fail" };

/** Horizontal/vertical grid used when placing new nodes. Matches the seeded layout spacing. */
export const NODE_WIDTH = 200;
export const NODE_HEIGHT = 56;
const STEP_X = 260;
const STEP_Y = 100;

export function emptyGraph(): Graph {
  return { nodes: [], edges: [] };
}

/** Normalise whatever the server returned into the builder's graph shape. */
export function toGraph(raw: unknown): Graph {
  const value = (raw ?? {}) as Partial<Graph>;
  return {
    nodes: Array.isArray(value.nodes) ? (value.nodes as GraphNode[]) : [],
    edges: Array.isArray(value.edges) ? (value.edges as GraphEdge[]) : [],
  };
}

// ---------------------------------------------------------------------------------------
// Ids

/** lowercase_snake from a label, always starting with a letter. */
export function snake(label: string): string {
  const base = label
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .replace(/^[0-9_]+/, "");
  return base || "node";
}

/** Unique node id: snake of the label plus the smallest free numeric suffix. */
export function makeNodeId(label: string, existing: Iterable<string>): string {
  const taken = new Set(existing);
  const base = snake(label).slice(0, 58);
  for (let n = 1; n < 10_000; n++) {
    const id = `${base}_${n}`;
    if (!taken.has(id)) return id;
  }
  throw new Error("Could not allocate a node id");
}

export function makeEdgeId(source: string, target: string, branch: Branch | null | undefined, existing: Iterable<string>): string {
  const taken = new Set(existing);
  const base = branch ? `e_${source}_${branch}_${target}` : `e_${source}_${target}`;
  if (!taken.has(base)) return base;
  for (let n = 2; ; n++) if (!taken.has(`${base}_${n}`)) return `${base}_${n}`;
}

export function uniqueName(label: string, nodes: GraphNode[]): string {
  const names = new Set(nodes.map((n) => n.name));
  if (!names.has(label)) return label;
  for (let n = 2; ; n++) if (!names.has(`${label} ${n}`)) return `${label} ${n}`;
}

// ---------------------------------------------------------------------------------------
// Config defaults from a Pydantic JSON schema

type SchemaLike = { properties?: Record<string, SchemaLike>; default?: unknown; required?: string[]; type?: unknown };

/** Defaults declared in a config schema. Required fields without a default start empty. */
export function defaultsFromSchema(schema: unknown): Record<string, unknown> {
  const s = (schema ?? {}) as SchemaLike;
  const out: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(s.properties ?? {})) {
    if (prop && "default" in prop) out[key] = structuredClone(prop.default);
    else if (s.required?.includes(key)) out[key] = prop?.type === "object" ? {} : "";
  }
  return out;
}

// ---------------------------------------------------------------------------------------
// Placement

function overlaps(a: Position, b: Position): boolean {
  return Math.abs(a.x - b.x) < NODE_WIDTH + 20 && Math.abs(a.y - b.y) < NODE_HEIGHT + 24;
}

/** First free slot at `start`, stepping down the column. */
export function freeSlot(graph: Graph, start: Position): Position {
  const pos = { ...start };
  for (let i = 0; i < 50 && graph.nodes.some((n) => overlaps(n.position, pos)); i++) pos.y += STEP_Y;
  return pos;
}

/** Where a node added by click goes: right of the anchor (or of the rightmost node), never on top of another. */
export function suggestPosition(graph: Graph, anchorId?: string | null): Position {
  const anchor = anchorId ? graph.nodes.find((n) => n.id === anchorId) : undefined;
  if (anchor) return freeSlot(graph, { x: anchor.position.x + STEP_X, y: anchor.position.y });
  if (graph.nodes.length === 0) return { x: 0, y: 0 };
  const rightmost = graph.nodes.reduce((a, b) => (b.position.x > a.position.x ? b : a));
  return freeSlot(graph, { x: rightmost.position.x + STEP_X, y: rightmost.position.y });
}

// ---------------------------------------------------------------------------------------
// Construction

export function createNode(args: {
  type: NodeType;
  label: string;
  configSchema?: unknown;
  position: Position;
  graph: Graph;
}): GraphNode {
  const { type, label, configSchema, position, graph } = args;
  const config = defaultsFromSchema(configSchema);
  if (type === "end" && config.output === undefined) config.output = "=nodes";
  return {
    id: makeNodeId(label, graph.nodes.map((n) => n.id)),
    type,
    name: uniqueName(label, graph.nodes),
    position: { x: Math.round(position.x), y: Math.round(position.y) },
    config,
    map: null,
    error_policy: { ...DEFAULT_ERROR_POLICY },
    notes: null,
  };
}

// ---------------------------------------------------------------------------------------
// Connections

export type ConnectResult = { ok: true; graph: Graph; edge: GraphEdge } | { ok: false; reason: string };

export function wouldCreateCycle(graph: Graph, source: string, target: string): boolean {
  if (source === target) return true;
  const out = new Map<string, string[]>();
  for (const e of graph.edges) out.set(e.source, [...(out.get(e.source) ?? []), e.target]);
  const stack = [target];
  const seen = new Set<string>();
  while (stack.length) {
    const id = stack.pop()!;
    if (id === source) return true;
    if (seen.has(id)) continue;
    seen.add(id);
    stack.push(...(out.get(id) ?? []));
  }
  return false;
}

export function connect(graph: Graph, source: string, target: string, branch: Branch | null = null): ConnectResult {
  const s = graph.nodes.find((n) => n.id === source);
  const t = graph.nodes.find((n) => n.id === target);
  if (!s || !t) return { ok: false, reason: "Both ends must be nodes in this pipeline." };
  if (source === target) return { ok: false, reason: "A node cannot connect to itself." };
  if (t.type === "trigger") return { ok: false, reason: "The trigger cannot have incoming edges." };
  if (s.type === "end") return { ok: false, reason: "End nodes cannot have outgoing edges." };
  if ((branch === "true" || branch === "false") && s.type !== "condition")
    return { ok: false, reason: "True and false branches can only leave a condition." };
  if (s.type === "condition" && branch === null) return { ok: false, reason: "Connect from the true or false handle." };
  if (graph.edges.some((e) => e.source === source && e.target === target && (e.branch ?? null) === branch))
    return { ok: false, reason: "These nodes are already connected." };
  if (wouldCreateCycle(graph, source, target)) return { ok: false, reason: "This edge would create a cycle." };
  const edge: GraphEdge = { id: makeEdgeId(source, target, branch, graph.edges.map((e) => e.id)), source, target, branch };
  return { ok: true, graph: { ...graph, edges: [...graph.edges, edge] }, edge };
}

// ---------------------------------------------------------------------------------------
// Edits

export function removeElements(graph: Graph, nodeIds: Iterable<string>, edgeIds: Iterable<string> = []): Graph {
  const nodes = new Set(nodeIds);
  const edges = new Set(edgeIds);
  return {
    nodes: graph.nodes.filter((n) => !nodes.has(n.id)),
    edges: graph.edges.filter((e) => !edges.has(e.id) && !nodes.has(e.source) && !nodes.has(e.target)),
  };
}

export type NodePatch = Partial<Pick<GraphNode, "name" | "notes" | "map" | "error_policy" | "config" | "position">>;

export function updateNode(graph: Graph, id: string, patch: NodePatch): Graph {
  return { ...graph, nodes: graph.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)) };
}

export function updateConfig(graph: Graph, id: string, config: Record<string, unknown>): Graph {
  return updateNode(graph, id, { config });
}

export function setPositions(graph: Graph, positions: Record<string, Position>): Graph {
  return {
    ...graph,
    nodes: graph.nodes.map((n) => (positions[n.id] ? { ...n, position: { x: positions[n.id]!.x, y: positions[n.id]!.y } } : n)),
  };
}

export function setEdgeBranch(graph: Graph, edgeId: string, branch: Branch | null): Graph {
  return { ...graph, edges: graph.edges.map((e) => (e.id === edgeId ? { ...e, branch } : e)) };
}

// ---------------------------------------------------------------------------------------
// Dirty check

/** Deterministic JSON: sorted keys, undefined dropped, positions rounded to 0.1px. */
export function canonical(value: unknown): string {
  return JSON.stringify(sortValue(value));
}

function sortValue(value: unknown, key?: string): unknown {
  if (Array.isArray(value)) return value.map((v) => sortValue(v));
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(obj).sort()) {
      if (obj[k] === undefined) continue;
      out[k] = sortValue(obj[k], k);
    }
    return out;
  }
  if (typeof value === "number" && (key === "x" || key === "y")) return Math.round(value * 10) / 10;
  return value;
}

export function isDirty(saved: Graph | null, current: Graph): boolean {
  if (!saved) return current.nodes.length > 0 || current.edges.length > 0;
  return canonical(saved) !== canonical(current);
}

// ---------------------------------------------------------------------------------------
// Reducer

export interface BuilderState {
  graph: Graph;
  saved: Graph | null;
}

export type BuilderAction =
  | { type: "load"; graph: Graph; saved?: Graph | null }
  | { type: "restore"; graph: Graph }
  | { type: "saved"; graph: Graph }
  | { type: "addNode"; node: GraphNode; connectFrom?: string | null }
  | { type: "remove"; nodeIds?: string[]; edgeIds?: string[] }
  | { type: "connect"; source: string; target: string; branch: Branch | null }
  | { type: "updateNode"; id: string; patch: NodePatch }
  | { type: "positions"; positions: Record<string, Position> }
  | { type: "edgeBranch"; id: string; branch: Branch | null };

export function initialState(saved: Graph | null): BuilderState {
  return { graph: saved ?? emptyGraph(), saved };
}

export function graphReducer(state: BuilderState, action: BuilderAction): BuilderState {
  switch (action.type) {
    case "load":
      return { graph: action.graph, saved: action.saved === undefined ? action.graph : action.saved };
    case "restore":
      return { ...state, graph: action.graph };
    case "saved":
      return { graph: action.graph, saved: action.graph };
    case "addNode": {
      let graph: Graph = { ...state.graph, nodes: [...state.graph.nodes, action.node] };
      if (action.connectFrom) {
        const source = graph.nodes.find((n) => n.id === action.connectFrom);
        const branch: Branch | null = source?.type === "condition" ? (graph.edges.some((e) => e.source === source.id && e.branch === "true") ? "false" : "true") : null;
        const result = connect(graph, action.connectFrom, action.node.id, branch);
        if (result.ok) graph = result.graph;
      }
      return { ...state, graph };
    }
    case "remove":
      return { ...state, graph: removeElements(state.graph, action.nodeIds ?? [], action.edgeIds ?? []) };
    case "connect": {
      const result = connect(state.graph, action.source, action.target, action.branch);
      return result.ok ? { ...state, graph: result.graph } : state;
    }
    case "updateNode":
      return { ...state, graph: updateNode(state.graph, action.id, action.patch) };
    case "positions":
      return { ...state, graph: setPositions(state.graph, action.positions) };
    case "edgeBranch":
      return { ...state, graph: setEdgeBranch(state.graph, action.id, action.branch) };
  }
}

// ---------------------------------------------------------------------------------------
// Derived data

export function isFallback(policy: ErrorPolicy | undefined): boolean {
  return policy?.mode === "fallback" || policy?.then === "fallback";
}

/** Example input for a manual run: the trigger input_schema property defaults. */
export function triggerInputDefaults(graph: Graph): Record<string, unknown> {
  const trigger = graph.nodes.find((n) => n.type === "trigger");
  const schema = (trigger?.config.input_schema ?? {}) as SchemaLike;
  const out: Record<string, unknown> = {};
  for (const [key, prop] of Object.entries(schema.properties ?? {})) {
    if (prop && "default" in prop) out[key] = prop.default;
    else if (prop?.type === "string") out[key] = "";
    else if (prop?.type === "integer" || prop?.type === "number") out[key] = 0;
    else if (prop?.type === "boolean") out[key] = false;
    else if (prop?.type === "array") out[key] = [];
    else if (prop?.type === "object") out[key] = {};
    else out[key] = null;
  }
  return out;
}

/** Ids of nodes upstream of `id` (transitively). */
export function upstreamOf(graph: Graph, id: string): string[] {
  const incoming = new Map<string, string[]>();
  for (const e of graph.edges) incoming.set(e.target, [...(incoming.get(e.target) ?? []), e.source]);
  const seen = new Set<string>();
  const stack = [...(incoming.get(id) ?? [])];
  while (stack.length) {
    const n = stack.pop()!;
    if (seen.has(n)) continue;
    seen.add(n);
    stack.push(...(incoming.get(n) ?? []));
  }
  return graph.nodes.map((n) => n.id).filter((n) => seen.has(n));
}

/** Names offered by `{{` autocomplete in a node's templates. */
export function templateCompletions(graph: Graph, nodeId: string | null, variableKeys: string[]): string[] {
  const out = new Set<string>(["input"]);
  const trigger = graph.nodes.find((n) => n.type === "trigger");
  const inputSchema = (trigger?.config.input_schema ?? {}) as SchemaLike;
  for (const key of Object.keys(inputSchema.properties ?? {})) out.add(`input.${key}`);
  const upstream = nodeId ? upstreamOf(graph, nodeId) : graph.nodes.map((n) => n.id);
  for (const id of upstream) if (id !== nodeId) out.add(`nodes.${id}.output`);
  const node = nodeId ? graph.nodes.find((n) => n.id === nodeId) : undefined;
  if (node?.map) out.add(node.map.item_name || "item");
  for (const key of variableKeys) {
    out.add(`vars.${key}`);
    out.add(key);
  }
  return [...out];
}
