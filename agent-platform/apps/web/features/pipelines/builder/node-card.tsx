"use client";

import { Handle, type Node, type NodeProps, Position } from "@xyflow/react";
import { Layers } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

import type { GraphNode } from "../graph";
import { NODE_ICONS } from "../node-meta";

export type PipelineNodeData = {
  node: GraphNode;
  summary: string;
  issue: "error" | "warning" | null;
  showErrorHandle: boolean;
};

export type PipelineFlowNode = Node<PipelineNodeData, "pipeline">;

function BranchHandle({ id, top, label }: { id: "true" | "false"; top: string; label: string }) {
  return (
    <>
      <Handle id={id} type="source" position={Position.Right} style={{ top }} aria-label={`${label} branch`} />
      <span className="pointer-events-none absolute right-2 -translate-y-1/2 font-mono text-[10px] leading-none text-fg-subtle" style={{ top }}>
        {label}
      </span>
    </>
  );
}

function PipelineNodeCard({ data, selected }: NodeProps<PipelineFlowNode>) {
  const { node, summary, issue, showErrorHandle } = data;
  const Icon = NODE_ICONS[node.type];
  const isCondition = node.type === "condition";
  return (
    <div
      className={cn(
        "relative w-[200px] rounded-md border bg-surface text-left",
        issue === "error" ? "border-danger ring-2 ring-danger/20" : issue === "warning" ? "border-warn" : "border-border-strong",
        selected && !issue && "border-ring ring-2 ring-ring/25",
        selected && issue && "ring-ring/30",
        node.map && "shadow-[3px_3px_0_-1px_var(--surface),3px_3px_0_0_var(--border-strong)]",
      )}
      data-node-id={node.id}
    >
      {node.type !== "trigger" ? <Handle id="in" type="target" position={Position.Left} aria-label="Input" /> : null}
      <div className={cn("flex h-7 items-center gap-1.5 border-b border-border px-2", isCondition && "pr-10")}>
        <Icon className="size-3.5 shrink-0 text-fg-muted" aria-hidden />
        <span className="min-w-0 flex-1 truncate text-xs font-medium text-fg">{node.name}</span>
        {node.map ? (
          <span title={`Runs once per item of ${node.map.over || "…"}`} className="flex shrink-0 items-center text-fg-subtle">
            <Layers className="size-3" aria-label="Mapped" />
          </span>
        ) : null}
      </div>
      <div className={cn("truncate px-2 py-1 font-mono text-2xs text-fg-muted", isCondition && "pr-10")} title={summary}>
        {node.map ? `map over ${node.map.over || "…"}` : summary}
      </div>
      {isCondition ? (
        <>
          <BranchHandle id="true" top="32%" label="true" />
          <BranchHandle id="false" top="72%" label="false" />
        </>
      ) : node.type !== "end" ? (
        <Handle id="out" type="source" position={Position.Right} aria-label="Output" />
      ) : null}
      {showErrorHandle && node.type !== "end" ? (
        <Handle id="error" type="source" position={Position.Bottom} className="error-handle" aria-label="Error branch" style={{ left: "78%" }} />
      ) : null}
    </div>
  );
}

export const PipelineNode = React.memo(PipelineNodeCard);
