"use client";

import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { PageContainer } from "@/components/shell/page-container";
import { DataTable } from "@/components/ui/data-table";
import { PageHeader } from "@/components/ui/page";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status";
import { useExecutions } from "@/features/executions/queries";
import type { Schemas } from "@/lib/api/client";
import { compact, dateTime, duration, relativeTime, shortId, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

type Status = Schemas["ExecutionStatus"];

const VIEWS: { id: string; label: string; statuses?: Status[] }[] = [
  { id: "all", label: "All" },
  { id: "active", label: "Active", statuses: ["queued", "running", "resuming", "waiting_for_tool", "waiting_for_timer"] },
  { id: "review", label: "Needs review", statuses: ["paused_for_review", "paused"] },
  { id: "failed", label: "Failed", statuses: ["failed"] },
  { id: "completed", label: "Completed", statuses: ["completed"] },
  { id: "cancelled", label: "Cancelled", statuses: ["cancelled"] },
];

function ExecutionsView() {
  const router = useRouter();
  const params = useSearchParams();
  const view = VIEWS.find((v) => v.id === params.get("view")) ?? VIEWS[0]!;
  const [offset, setOffset] = React.useState(0);
  const pipelineId = params.get("pipeline") ?? undefined;
  const { data, isPending, error, refetch } = useExecutions({ status: view.statuses, pipelineId, offset });

  return (
    <PageContainer>
      <PageHeader title="Executions" description="Every run of every pipeline. Open one to watch it live, inspect calls and replay its snapshot." />
      <div className="flex flex-wrap items-center gap-1" role="tablist" aria-label="Filter by status">
        {VIEWS.map((v) => (
          <button
            key={v.id}
            role="tab"
            aria-selected={v.id === view.id}
            onClick={() => {
              setOffset(0);
              const next = new URLSearchParams(params);
              if (v.id === "all") next.delete("view");
              else next.set("view", v.id);
              router.replace(`/executions${next.size ? `?${next}` : ""}`);
            }}
            className={cn(
              "h-7 rounded-md px-2.5 text-xs text-fg-muted transition-colors duration-100 hover:bg-subtle hover:text-fg",
              v.id === view.id && "bg-surface font-medium text-fg shadow-[0_0_0_1px_var(--border)]",
            )}
          >
            {v.label}
          </button>
        ))}
      </div>
      {isPending ? (
        <LoadingState rows={10} />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : (
        <DataTable
          rows={data.items}
          getRowId={(e) => e.id}
          onRowClick={(e) => router.push(`/executions/${e.id}`)}
          server={{ total: data.total, limit: data.limit, offset: data.offset, onOffsetChange: setOffset }}
          empty={view.id === "all" ? "No executions yet. Run a pipeline from its builder." : "No executions in this view."}
          columns={[
            { id: "id", header: "Execution", cell: (e) => <span className="font-mono text-xs">{shortId(e.id)}</span> },
            {
              id: "pipeline",
              header: "Pipeline",
              cell: (e) => (
                <span>
                  {e.pipeline_name} <span className="text-xs text-fg-subtle">v{e.pipeline_version}</span>
                </span>
              ),
            },
            { id: "status", header: "Status", cell: (e) => <StatusIndicator kind="execution" value={e.status} /> },
            { id: "trigger", header: "Trigger", cell: (e) => <span className="capitalize text-fg-muted">{e.trigger}</span> },
            { id: "started", header: "Started", cell: (e) => <span className="text-fg-muted" title={dateTime(e.started_at ?? e.created_at)}>{relativeTime(e.started_at ?? e.created_at)}</span> },
            { id: "duration", header: "Duration", align: "right", cell: (e) => duration(e.started_at, e.finished_at) },
            { id: "tokens", header: "Tokens", align: "right", cell: (e) => compact(e.total_tokens) },
            { id: "cost", header: "Est. cost", align: "right", cell: (e) => usd(e.estimated_cost) },
          ]}
        />
      )}
    </PageContainer>
  );
}

export default function ExecutionsPage() {
  return (
    <React.Suspense>
      <ExecutionsView />
    </React.Suspense>
  );
}
