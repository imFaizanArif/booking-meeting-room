import {
  Bot,
  Clock,
  Flag,
  GitBranch,
  type LucideIcon,
  Play,
  Send,
  Shuffle,
  Sparkles,
  UserCheck,
  Wrench,
} from "lucide-react";

import type { GraphNode, NodeType } from "./graph";

export const NODE_ICONS: Record<NodeType, LucideIcon> = {
  trigger: Play,
  llm: Sparkles,
  agent: Bot,
  mcp_tool: Wrench,
  condition: GitBranch,
  transform: Shuffle,
  human_approval: UserCheck,
  notification: Send,
  delay: Clock,
  end: Flag,
};

export const PALETTE_GROUPS: { label: string; types: NodeType[] }[] = [
  { label: "Start and end", types: ["trigger", "end"] },
  { label: "Models", types: ["llm", "agent"] },
  { label: "Tools and data", types: ["mcp_tool", "transform", "notification"] },
  { label: "Flow control", types: ["condition", "human_approval", "delay"] },
];

export interface SummaryContext {
  modelName?: (id: string) => string | undefined;
  templateName?: (id: string) => string | undefined;
}

function truncate(value: string, n = 48): string {
  const flat = value.replace(/\s+/g, " ").trim();
  return flat.length > n ? `${flat.slice(0, n - 1)}…` : flat;
}

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

/** The one secondary line under a node's name on the canvas. */
export function nodeSummary(node: GraphNode, ctx: SummaryContext = {}): string {
  const c = node.config ?? {};
  switch (node.type) {
    case "trigger": {
      const props = Object.keys(((c.input_schema as { properties?: object } | undefined)?.properties ?? {}) as object);
      const kinds = [c.allow_manual !== false && "manual", c.allow_schedule !== false && "schedule", c.allow_webhook === true && "webhook"].filter(Boolean);
      return `${props.length} input${props.length === 1 ? "" : "s"} · ${kinds.join(", ") || "no triggers"}`;
    }
    case "llm":
    case "agent": {
      const id = str(c.model_id);
      const model = id ? (ctx.modelName?.(id) ?? "Unknown model") : "Workspace default model";
      if (node.type === "agent") {
        const tools = Array.isArray(c.tool_allowlist) ? c.tool_allowlist.length : 0;
        return `${model} · ${tools} tool${tools === 1 ? "" : "s"}`;
      }
      return model;
    }
    case "mcp_tool":
      return str(c.tool) || "No tool selected";
    case "condition":
      return str(c.expression) ? truncate(str(c.expression)) : "No expression";
    case "transform": {
      const mode = str(c.mode) || "expression";
      if (mode === "jsonpath") return truncate(`jsonpath ${str(c.jsonpath)}`);
      if (mode === "template") return `template · ${Object.keys((c.template as object) ?? {}).length} keys`;
      return str(c.expression) ? truncate(str(c.expression)) : "No expression";
    }
    case "human_approval":
      return truncate(str(c.title) || "Review required");
    case "notification": {
      const n = Array.isArray(c.channel_ids) ? c.channel_ids.length : 0;
      return `${n} channel${n === 1 ? "" : "s"}`;
    }
    case "delay":
      if (typeof c.seconds === "number") return `Wait ${formatSeconds(c.seconds)}`;
      if (str(c.until)) return truncate(`Until ${str(c.until)}`);
      return "No duration";
    case "end": {
      const out = c.output;
      if (typeof out === "string") return truncate(`Output ${out}`);
      if (out && typeof out === "object") return truncate(`Output ${Object.keys(out).join(", ")}`);
      return "Output";
    }
  }
}

export function formatSeconds(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${+(s / 3600).toFixed(1)}h`;
  return `${+(s / 86400).toFixed(1)}d`;
}
