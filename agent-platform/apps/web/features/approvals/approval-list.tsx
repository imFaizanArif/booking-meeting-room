"use client";

import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { RiskBadge, StatusIndicator } from "@/components/ui/status";
import type { Schemas } from "@/lib/api/client";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Inbox } from "lucide-react";

type Approval = Schemas["ApprovalOut"];

export const KIND_LABEL: Record<Schemas["ApprovalKind"], string> = {
  tool_call: "Tool call",
  data_review: "Data review",
  outcome_unknown: "Outcome unknown",
};

interface Props {
  items: Approval[] | undefined;
  selectedId?: string;
  isPending: boolean;
  error: unknown;
  onRetry: () => void;
  filter: string;
}

export function ApprovalList({ items, selectedId, isPending, error, onRetry, filter }: Props) {
  if (isPending) return <LoadingState rows={6} className="p-3" />;
  if (error) return <ErrorState error={error} onRetry={onRetry} className="m-3" />;
  if (!items?.length) {
    return (
      <EmptyState
        icon={Inbox}
        className="m-3"
        title={filter === "pending" ? "Nothing to review" : "No approvals yet"}
        body={filter === "pending" ? "Gated tool calls and review steps land here when an execution pauses." : undefined}
      />
    );
  }
  return (
    <ul className="flex flex-col" aria-label="Approvals">
      {items.map((a) => {
        const selected = a.id === selectedId;
        return (
          <li key={a.id}>
            <Link
              href={`/approvals/${a.id}${filter !== "pending" ? `?filter=${filter}` : ""}`}
              aria-current={selected ? "true" : undefined}
              className={cn(
                "flex flex-col gap-1 border-b border-border px-4 py-2.5 transition-colors duration-100 hover:bg-subtle",
                selected && "bg-subtle",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-sm font-medium">{a.tool_name ?? a.title}</span>
                <span className="shrink-0 text-2xs text-fg-subtle">{relativeTime(a.created_at)}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-xs text-fg-muted">
                  {a.server_slug ? `${a.server_slug} · ` : ""}
                  {a.pipeline_name}
                </span>
                {a.status === "pending" ? <RiskBadge level={a.risk_level} /> : <StatusIndicator kind="approval" value={a.status} />}
              </div>
              {a.kind !== "tool_call" ? (
                <div>
                  <Badge tone={a.kind === "outcome_unknown" ? "warn" : "neutral"}>{KIND_LABEL[a.kind]}</Badge>
                </div>
              ) : null}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
