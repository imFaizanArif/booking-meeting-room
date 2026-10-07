import type { Schemas } from "@/lib/api/client";
import { shortTime, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

type Event = Schemas["ExecutionEventOut"];

const TONE: Record<string, string> = {
  failed: "text-danger",
  rejected: "text-danger",
  completed: "text-ok",
  awaiting_approval: "text-warn",
  paused: "text-warn",
  created: "text-warn",
  retrying: "text-warn",
};

function tone(type: string): string {
  const key = type.split(".")[1] ?? "";
  if (type === "approval.created") return "text-warn";
  return TONE[key] ?? "text-fg-muted";
}

function describe(e: Event): string {
  const p = e.payload as Record<string, unknown>;
  const s = (k: string) => (p[k] == null ? "" : String(p[k]));
  switch (e.type) {
    case "llm.requested":
      return `${s("model")} · ${s("messages")} messages, ${s("tools")} tools`;
    case "llm.completed":
      return `${s("model")} · ${s("input_tokens")}→${s("output_tokens")} tokens · ${usd(s("estimated_cost"))} · ${s("latency_ms")} ms · ${s("summary")}`;
    case "tool.requested":
    case "tool.executing":
    case "tool.approved":
    case "tool.rejected":
    case "tool.awaiting_approval":
      return s("tool") + (p["attempt"] ? ` · attempt ${s("attempt")}` : "");
    case "tool.completed":
      return `${s("tool")} · ${s("duration_ms")} ms`;
    case "tool.failed":
      return `${s("tool")} · ${String((p["error"] as { message?: string } | undefined)?.message ?? "")}`;
    case "node.failed":
      return String((p["error"] as { message?: string } | undefined)?.message ?? "failed");
    case "node.retrying":
      return `attempt ${s("attempt")} failed, retrying in ${s("delay_s")}s`;
    case "approval.created":
      return s("title");
    case "approval.decided":
      return `${s("action")} by ${s("decided_by")}${p["reason"] ? ` · ${s("reason")}` : ""}`;
    case "execution.failed":
      return String((p["error"] as { message?: string } | undefined)?.message ?? "");
    default:
      return s("status") || s("name") || "";
  }
}

export function Timeline({ events, onSelectNode, compact }: { events: Event[]; onSelectNode?: (id: string) => void; compact?: boolean }) {
  if (!events.length) return <p className="px-4 py-4 text-sm text-fg-muted">No events yet.</p>;
  if (compact) {
    return (
      <ol className="text-xs" aria-label="Recent events">
        {events.map((e) => (
          <li key={e.seq} className="flex flex-col gap-0.5 border-b border-border px-4 py-1.5 last:border-b-0">
            <div className="flex items-center gap-2 font-mono">
              <span className="tabular text-fg-subtle">{shortTime(e.created_at)}</span>
              <span className={cn(tone(e.type))}>{e.type}</span>
              {e.node_id ? (
                <button type="button" onClick={() => onSelectNode?.(e.node_id!)} className="ml-auto truncate text-fg-muted hover:text-fg hover:underline">
                  {e.node_id}
                </button>
              ) : null}
            </div>
            {describe(e) ? <p className="truncate text-fg-muted" title={describe(e)}>{describe(e)}</p> : null}
          </li>
        ))}
      </ol>
    );
  }
  return (
    <ol className="font-mono text-xs" aria-label="Execution events">
      {events.map((e) => (
        <li key={e.seq} className="grid grid-cols-[3rem_4.5rem_11rem_8rem_1fr] items-baseline gap-2 border-b border-border px-2 py-1 last:border-b-0 hover:bg-subtle">
          <span className="tabular text-fg-subtle">#{e.seq}</span>
          <span className="tabular text-fg-subtle">{shortTime(e.created_at)}</span>
          <span className={cn("truncate", tone(e.type))}>{e.type}</span>
          {e.node_id ? (
            <button type="button" onClick={() => onSelectNode?.(e.node_id!)} className="truncate text-left text-fg-muted hover:text-fg hover:underline">
              {e.node_id}
            </button>
          ) : (
            <span />
          )}
          <span className="truncate font-sans text-fg-muted" title={describe(e)}>
            {describe(e)}
          </span>
        </li>
      ))}
    </ol>
  );
}
