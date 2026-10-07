import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import type { Tone } from "./badge";

type ExecutionStatus = Schemas["ExecutionStatus"];
type NodeStatus = Schemas["NodeStatus"];
type ToolCallStatus = Schemas["ToolCallStatus"];
type ApprovalStatus = Schemas["ApprovalStatus"];
type ServerStatus = Schemas["ServerStatus"];

interface StatusSpec {
  tone: Tone;
  label: string;
  live?: boolean;
}

const EXECUTION: Record<ExecutionStatus, StatusSpec> = {
  created: { tone: "neutral", label: "Created" },
  queued: { tone: "neutral", label: "Queued", live: true },
  running: { tone: "info", label: "Running", live: true },
  waiting_for_tool: { tone: "info", label: "Waiting for tool", live: true },
  waiting_for_timer: { tone: "neutral", label: "Waiting for timer" },
  paused_for_review: { tone: "warn", label: "Needs review" },
  paused: { tone: "warn", label: "Paused" },
  resuming: { tone: "info", label: "Resuming", live: true },
  completed: { tone: "ok", label: "Completed" },
  failed: { tone: "danger", label: "Failed" },
  cancelled: { tone: "neutral", label: "Cancelled" },
};

const NODE: Record<NodeStatus, StatusSpec> = {
  pending: { tone: "neutral", label: "Pending" },
  running: { tone: "info", label: "Running", live: true },
  completed: { tone: "ok", label: "Done" },
  failed: { tone: "danger", label: "Failed" },
  skipped: { tone: "neutral", label: "Skipped" },
  waiting: { tone: "warn", label: "Waiting" },
  retrying: { tone: "warn", label: "Retrying", live: true },
  cancelled: { tone: "neutral", label: "Cancelled" },
};

const TOOL_CALL: Record<ToolCallStatus, StatusSpec> = {
  pending: { tone: "neutral", label: "Pending" },
  awaiting_approval: { tone: "warn", label: "Awaiting approval" },
  approved: { tone: "info", label: "Approved" },
  executing: { tone: "info", label: "Executing", live: true },
  completed: { tone: "ok", label: "Completed" },
  failed: { tone: "danger", label: "Failed" },
  rejected: { tone: "danger", label: "Rejected" },
  cancelled: { tone: "neutral", label: "Cancelled" },
  timeout: { tone: "danger", label: "Timed out" },
  outcome_unknown: { tone: "warn", label: "Outcome unknown" },
};

const APPROVAL: Record<ApprovalStatus, StatusSpec> = {
  pending: { tone: "warn", label: "Pending" },
  approved: { tone: "ok", label: "Approved" },
  rejected: { tone: "danger", label: "Rejected" },
  superseded: { tone: "neutral", label: "Superseded" },
  expired: { tone: "neutral", label: "Expired" },
};

const SERVER: Record<ServerStatus, StatusSpec> = {
  disconnected: { tone: "neutral", label: "Idle" },
  connecting: { tone: "info", label: "Connecting", live: true },
  initializing: { tone: "info", label: "Initializing", live: true },
  discovering: { tone: "info", label: "Discovering", live: true },
  ready: { tone: "ok", label: "Ready" },
  reconnecting: { tone: "warn", label: "Reconnecting", live: true },
  failed: { tone: "danger", label: "Failed" },
};

const MAPS = { execution: EXECUTION, node: NODE, toolCall: TOOL_CALL, approval: APPROVAL, server: SERVER } as const;
type Kind = keyof typeof MAPS;

const DOT: Record<Tone, string> = {
  neutral: "bg-fg-subtle",
  info: "bg-info",
  warn: "bg-warn",
  ok: "bg-ok",
  danger: "bg-danger",
  outline: "bg-fg-subtle",
};
const TEXT: Record<Tone, string> = {
  neutral: "text-fg-muted",
  info: "text-info",
  warn: "text-warn",
  ok: "text-ok",
  danger: "text-danger",
  outline: "text-fg-muted",
};

export function statusSpec(kind: Kind, value: string): StatusSpec {
  return (MAPS[kind] as Record<string, StatusSpec>)[value] ?? { tone: "neutral", label: value };
}

/** Dot + label. Colour carries meaning; the label keeps it accessible without colour. */
export function StatusIndicator({ kind, value, className, compact }: { kind: Kind; value: string; className?: string; compact?: boolean }) {
  const spec = statusSpec(kind, value);
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium", TEXT[spec.tone], className)}>
      <span className={cn("size-1.5 shrink-0 rounded-full", DOT[spec.tone], spec.live && "anim-pulse")} aria-hidden />
      {compact ? <span className="sr-only">{spec.label}</span> : spec.label}
    </span>
  );
}

export function RiskBadge({ level }: { level: string | null | undefined }) {
  const tone: Tone = level === "critical" || level === "high" ? "danger" : level === "medium" ? "warn" : "neutral";
  return (
    <span className={cn("inline-flex items-center gap-1 text-xs font-medium", TEXT[tone])}>
      <span className={cn("inline-block h-2.5 w-[3px] rounded-[1px]", DOT[tone])} aria-hidden />
      {level ? level[0]!.toUpperCase() + level.slice(1) : "—"}
    </span>
  );
}
