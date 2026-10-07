"use client";

import { Background, Handle, type Node, type NodeProps, Position, ReactFlow, type Edge } from "@xyflow/react";
import "@xyflow/react/dist/base.css";
import { Bot, Clock, Flag, GitBranch, Hand, Bell, Play, Shuffle, Sparkles, Wrench } from "lucide-react";
import * as React from "react";

import { statusSpec } from "@/components/ui/status";
import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

type Graph = Schemas["PipelineGraph-Output"];
type NodeRow = Schemas["ExecutionNodeOut"];

const ICONS: Record<string, typeof Bot> = {
  trigger: Play, llm: Sparkles, agent: Bot, mcp_tool: Wrench, condition: GitBranch, transform: Shuffle,
  human_approval: Hand, notification: Bell, delay: Clock, end: Flag,
};

const RING: Record<string, string> = {
  info: "border-info shadow-[0_0_0_3px_var(--info-bg)]",
  warn: "border-warn shadow-[0_0_0_3px_var(--warn-bg)]",
  ok: "border-ok/60",
  danger: "border-danger shadow-[0_0_0_3px_var(--danger-bg)]",
  neutral: "border-border-strong",
  outline: "border-border-strong",
};

interface Data extends Record<string, unknown> {
  name: string;
  type: string;
  status?: string;
  attempts?: number;
  waiting?: boolean;
  mapped?: boolean;
  selected?: boolean;
}

function StatusNode({ data }: NodeProps<Node<Data>>) {
  const Icon = ICONS[data.type] ?? Wrench;
  const spec = data.waiting ? { tone: "warn" as const, label: "Needs review", live: false } : data.status ? statusSpec("node", data.status) : null;
  return (
    <div
      className={cn(
        "w-[184px] rounded-md border bg-surface px-3 py-2 text-left transition-shadow duration-150",
        spec ? RING[spec.tone] : "border-border",
        !data.status && "opacity-60",
        data.selected && "outline outline-2 outline-offset-2 outline-fg",
      )}
    >
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-border-strong" />
      <div className="flex items-center gap-1.5">
        <Icon className="size-3.5 shrink-0 text-fg-muted" aria-hidden />
        <span className="truncate text-sm font-medium">{data.name}</span>
      </div>
      <div className="mt-1 flex items-center justify-between gap-2 text-xs text-fg-muted">
        <span>{spec?.label ?? "Not reached"}</span>
        <span className="tabular">
          {[data.mapped ? "map" : null, data.attempts && data.attempts > 1 ? `${data.attempts} attempts` : null].filter(Boolean).join(" · ")}
        </span>
      </div>
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-border-strong" />
    </div>
  );
}

const nodeTypes = { status: StatusNode };

export function StatusGraph({ graph, nodes, waitingNodeIds, selected, onSelect }: {
  graph: Graph;
  nodes: NodeRow[];
  waitingNodeIds: Set<string>;
  selected: string | null;
  onSelect: (nodeId: string | null) => void;
}) {
  const rows = React.useMemo(() => new Map(nodes.map((n) => [n.node_id, n])), [nodes]);
  const flowNodes: Node<Data>[] = graph.nodes.map((n) => ({
    id: n.id,
    type: "status",
    position: { x: n.position?.x ?? 0, y: n.position?.y ?? 0 },
    data: {
      name: n.name,
      type: n.type,
      status: rows.get(n.id)?.status,
      attempts: rows.get(n.id)?.attempts,
      waiting: waitingNodeIds.has(n.id),
      mapped: !!n.map,
      selected: selected === n.id,
    },
    draggable: false,
    connectable: false,
  }));
  const flowEdges: Edge[] = graph.edges.map((e) => {
    const sourceStatus = rows.get(e.source)?.status;
    const reached = sourceStatus === "completed" && !!rows.get(e.target);
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      type: "smoothstep",
      label: e.branch ?? undefined,
      labelStyle: { fontSize: 10, fill: "var(--fg-muted)" },
      labelBgStyle: { fill: "var(--bg)" },
      style: { stroke: reached ? "var(--fg-muted)" : "var(--border-strong)", strokeDasharray: reached ? undefined : "4 3" },
    };
  });
  return (
    <div className="h-full min-h-[360px] w-full">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.08, maxZoom: 1 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, node) => onSelect(node.id)}
        onPaneClick={() => onSelect(null)}
        proOptions={{ hideAttribution: true }}
        minZoom={0.3}
      >
        <Background gap={16} size={1} color="var(--canvas-dot)" />
      </ReactFlow>
    </div>
  );
}
