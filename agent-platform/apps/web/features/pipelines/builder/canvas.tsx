"use client";

import "@xyflow/react/dist/base.css";

import {
  Background,
  BackgroundVariant,
  type Connection,
  Controls,
  type Edge,
  type EdgeChange,
  MarkerType,
  MiniMap,
  type NodeChange,
  ReactFlow,
  useReactFlow,
} from "@xyflow/react";
import * as React from "react";

import type { Branch, BuilderAction, Graph, NodeType, Position } from "../graph";
import { isFallback } from "../graph";
import styles from "./canvas.module.css";
import { PipelineNode, type PipelineFlowNode } from "./node-card";

const nodeTypes = { pipeline: PipelineNode };

export interface Selection {
  nodes: string[];
  edges: string[];
}

export const NODE_DRAG_MIME = "application/x-pipeline-node-type";

interface CanvasProps {
  graph: Graph;
  selection: Selection;
  onSelectionChange: (selection: Selection) => void;
  dispatch: React.Dispatch<BuilderAction>;
  summaries: Record<string, string>;
  issues: Record<string, "error" | "warning">;
  readOnly?: boolean;
  showMinimap: boolean;
  onDropType: (type: NodeType, position: Position) => void;
  onConnectRejected: (reason: string) => void;
  validateConnection: (source: string, target: string, branch: Branch | null) => string | null;
}

function branchFromHandle(handle: string | null | undefined): Branch | null {
  return handle === "true" || handle === "false" || handle === "error" ? handle : null;
}

export function BuilderCanvas({
  graph,
  selection,
  onSelectionChange,
  dispatch,
  summaries,
  issues,
  readOnly,
  showMinimap,
  onDropType,
  onConnectRejected,
  validateConnection,
}: CanvasProps) {
  const flow = useReactFlow();
  const [measured, setMeasured] = React.useState<Record<string, { width: number; height: number }>>({});
  const cache = React.useRef(new Map<string, { key: unknown[]; node: PipelineFlowNode }>());

  const selectedNodes = React.useMemo(() => new Set(selection.nodes), [selection.nodes]);
  const selectedEdges = React.useMemo(() => new Set(selection.edges), [selection.edges]);

  const errorSources = React.useMemo(() => new Set(graph.edges.filter((e) => e.branch === "error").map((e) => e.source)), [graph.edges]);

  const nodes = React.useMemo<PipelineFlowNode[]>(() => {
    const next = new Map<string, { key: unknown[]; node: PipelineFlowNode }>();
    // eslint-disable-next-line react-hooks/refs -- the callback reads the identity cache below
    const out = graph.nodes.map((n) => {
      const issue = issues[n.id] ?? null;
      const showErrorHandle = isFallback(n.error_policy) || errorSources.has(n.id);
      const key = [n, summaries[n.id], issue, showErrorHandle, selectedNodes.has(n.id), measured[n.id], readOnly];
      const prev = cache.current.get(n.id);
      if (prev && prev.key.every((v, i) => v === key[i])) {
        next.set(n.id, prev);
        return prev.node;
      }
      const node: PipelineFlowNode = {
        id: n.id,
        type: "pipeline",
        position: n.position,
        data: { node: n, summary: summaries[n.id] ?? "", issue, showErrorHandle },
        selected: selectedNodes.has(n.id),
        measured: measured[n.id],
        deletable: !readOnly,
        draggable: !readOnly,
        connectable: !readOnly,
        ariaLabel: `${n.name} (${n.type.replace("_", " ")})`,
      };
      next.set(n.id, { key, node });
      return node;
    });
    // eslint-disable-next-line react-hooks/refs -- see above
    cache.current = next;
    return out;
  }, [graph.nodes, summaries, issues, errorSources, selectedNodes, measured, readOnly]);

  const edges = React.useMemo<Edge[]>(
    () =>
      graph.edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        sourceHandle: e.branch ?? "out",
        targetHandle: "in",
        type: "smoothstep",
        label: e.branch ?? undefined,
        labelBgPadding: [4, 2] as [number, number],
        labelBgBorderRadius: 3,
        selected: selectedEdges.has(e.id),
        className: e.branch === "error" ? "error-edge" : undefined,
        markerEnd: { type: MarkerType.ArrowClosed, width: 14, height: 14, color: e.branch === "error" ? "var(--danger)" : "var(--border-strong)" },
        deletable: !readOnly,
        ariaLabel: `Edge from ${e.source} to ${e.target}${e.branch ? ` (${e.branch})` : ""}`,
      })),
    [graph.edges, selectedEdges, readOnly],
  );

  const onNodesChange = React.useCallback(
    (changes: NodeChange<PipelineFlowNode>[]) => {
      const positions: Record<string, Position> = {};
      const dims: Record<string, { width: number; height: number }> = {};
      const removed: string[] = [];
      let nextSelected: Set<string> | null = null;
      for (const c of changes) {
        if (c.type === "position" && c.position) positions[c.id] = c.position;
        else if (c.type === "dimensions" && c.dimensions) dims[c.id] = c.dimensions;
        else if (c.type === "remove") removed.push(c.id);
        else if (c.type === "select") {
          nextSelected ??= new Set(selection.nodes);
          if (c.selected) nextSelected.add(c.id);
          else nextSelected.delete(c.id);
        }
      }
      if (Object.keys(dims).length) setMeasured((m) => ({ ...m, ...dims }));
      if (Object.keys(positions).length && !readOnly) dispatch({ type: "positions", positions });
      if (removed.length && !readOnly) dispatch({ type: "remove", nodeIds: removed });
      if (nextSelected || removed.length) {
        const nodesSel = [...(nextSelected ?? new Set(selection.nodes))].filter((id) => !removed.includes(id));
        onSelectionChange({ nodes: nodesSel, edges: selection.edges });
      }
    },
    [dispatch, onSelectionChange, readOnly, selection],
  );

  const onEdgesChange = React.useCallback(
    (changes: EdgeChange[]) => {
      const removed: string[] = [];
      let nextSelected: Set<string> | null = null;
      for (const c of changes) {
        if (c.type === "remove") removed.push(c.id);
        else if (c.type === "select") {
          nextSelected ??= new Set(selection.edges);
          if (c.selected) nextSelected.add(c.id);
          else nextSelected.delete(c.id);
        }
      }
      if (removed.length && !readOnly) dispatch({ type: "remove", edgeIds: removed });
      if (nextSelected || removed.length) {
        const edgesSel = [...(nextSelected ?? new Set(selection.edges))].filter((id) => !removed.includes(id));
        onSelectionChange({ nodes: selection.nodes, edges: edgesSel });
      }
    },
    [dispatch, onSelectionChange, readOnly, selection],
  );

  const onConnect = React.useCallback(
    (c: Connection) => {
      const branch = branchFromHandle(c.sourceHandle);
      const reason = validateConnection(c.source, c.target, branch);
      if (reason) onConnectRejected(reason);
      else dispatch({ type: "connect", source: c.source, target: c.target, branch });
    },
    [dispatch, onConnectRejected, validateConnection],
  );

  const isValidConnection = React.useCallback(
    (c: Connection | Edge) => validateConnection(c.source, c.target, branchFromHandle(c.sourceHandle)) === null,
    [validateConnection],
  );

  return (
    <div
      className="h-full w-full"
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes(NODE_DRAG_MIME)) {
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
        }
      }}
      onDrop={(e) => {
        const type = e.dataTransfer.getData(NODE_DRAG_MIME) as NodeType;
        if (!type || readOnly) return;
        e.preventDefault();
        const p = flow.screenToFlowPosition({ x: e.clientX, y: e.clientY });
        onDropType(type, { x: p.x - 100, y: p.y - 26 });
      }}
    >
      <ReactFlow<PipelineFlowNode, Edge>
        className={styles.flow}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        isValidConnection={isValidConnection}
        deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]}
        multiSelectionKeyCode={["Meta", "Control", "Shift"]}
        fitView
        fitViewOptions={{ padding: 0.2, maxZoom: 1.1 }}
        minZoom={0.25}
        maxZoom={2}
        snapToGrid
        snapGrid={[10, 10]}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: "smoothstep" }}
        connectionLineStyle={{ stroke: "var(--ring)", strokeWidth: 1.25 }}
        aria-label="Pipeline graph"
      >
        <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--canvas-dot)" />
        <Controls showInteractive={false} position="bottom-left" />
        {showMinimap ? <MiniMap pannable zoomable position="bottom-right" nodeColor="var(--muted)" nodeStrokeColor="var(--border-strong)" maskColor="color-mix(in oklch, var(--bg) 70%, transparent)" /> : null}
      </ReactFlow>
    </div>
  );
}
