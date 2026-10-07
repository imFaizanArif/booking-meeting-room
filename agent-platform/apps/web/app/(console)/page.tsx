"use client";

import { ArrowUpRight, CheckCircle2 } from "lucide-react";
import Link from "next/link";

import { PageContainer } from "@/components/shell/page-container";
import { DataTable } from "@/components/ui/data-table";
import { Metric, PageHeader, Panel, Section } from "@/components/ui/page";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { RiskBadge, StatusIndicator } from "@/components/ui/status";
import { useDashboard } from "@/features/dashboard/queries";
import { compact, dateTime, duration, relativeTime, shortId, usd } from "@/lib/format";

export default function DashboardPage() {
  const { data, isPending, error, refetch } = useDashboard();

  return (
    <PageContainer>
      <PageHeader title="Overview" description="What needs attention now, and what the platform did in the last 24 hours." />
      {isPending ? (
        <LoadingState rows={8} />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : (
        <>
          <Panel className="grid grid-cols-2 divide-x divide-y divide-border sm:grid-cols-3 sm:divide-y-0 lg:grid-cols-6">
            <Metric label="Running now" value={data.running.filter((e) => !["paused_for_review", "paused", "waiting_for_timer"].includes(e.status)).length} />
            <Metric label="Needs review" value={data.pending_approvals.length} tone={data.pending_approvals.length ? "warn" : undefined} />
            <Metric label="Failed · 24h" value={data.status_counts_24h["failed"] ?? 0} tone={(data.status_counts_24h["failed"] ?? 0) > 0 ? "danger" : undefined} />
            <Metric label="Executions · 24h" value={data.executions_24h} />
            <Metric label="Tokens · 24h" value={compact(data.tokens_24h)} />
            <Metric label="Est. cost · 24h" value={usd(data.cost_24h)} />
          </Panel>

          <div className="grid grid-cols-1 gap-8 xl:grid-cols-[minmax(0,1fr)_340px]">
            <div className="flex min-w-0 flex-col gap-8">
              <Section
                title="Needs review"
                description="Paused executions waiting on a decision. Oldest first."
                actions={
                  <Link href="/approvals" className="inline-flex items-center gap-1 text-xs text-fg-muted hover:text-fg">
                    Approval desk <ArrowUpRight className="size-3" />
                  </Link>
                }
              >
                {data.pending_approvals.length === 0 ? (
                  <p className="flex items-center gap-2 text-sm text-fg-muted">
                    <CheckCircle2 className="size-4 text-ok" aria-hidden /> Nothing is waiting on you.
                  </p>
                ) : (
                  <DataTable
                    rows={data.pending_approvals}
                    getRowId={(a) => a.id}
                    onRowClick={(a) => (window.location.href = `/approvals/${a.id}`)}
                    columns={[
                      { id: "title", header: "Action", cell: (a) => <span className="font-medium">{a.title}</span> },
                      { id: "pipeline", header: "Pipeline", cell: (a) => <span className="text-fg-muted">{a.pipeline_name}</span> },
                      { id: "risk", header: "Risk", cell: (a) => <RiskBadge level={a.risk_level} /> },
                      { id: "age", header: "Waiting", align: "right", cell: (a) => <span className="text-fg-muted">{relativeTime(a.created_at)}</span> },
                    ]}
                  />
                )}
              </Section>

              <Section title="Active executions" description="Queued, running, paused or waiting.">
                <DataTable
                  rows={data.running}
                  getRowId={(e) => e.id}
                  onRowClick={(e) => (window.location.href = `/executions/${e.id}`)}
                  empty="No active executions."
                  columns={[
                    { id: "id", header: "Execution", cell: (e) => <span className="font-mono text-xs">{shortId(e.id)}</span> },
                    { id: "pipeline", header: "Pipeline", cell: (e) => e.pipeline_name },
                    { id: "status", header: "Status", cell: (e) => <StatusIndicator kind="execution" value={e.status} /> },
                    { id: "trigger", header: "Trigger", cell: (e) => <span className="capitalize text-fg-muted">{e.trigger}</span> },
                    { id: "elapsed", header: "Elapsed", align: "right", cell: (e) => duration(e.started_at ?? e.created_at, null) },
                  ]}
                />
              </Section>
            </div>

            <div className="flex flex-col gap-8">
              <Section title="MCP servers">
                {data.unhealthy_servers.length === 0 ? (
                  <p className="flex items-center gap-2 text-sm text-fg-muted">
                    <CheckCircle2 className="size-4 text-ok" aria-hidden /> All active servers are healthy.
                  </p>
                ) : (
                  <ul className="flex flex-col divide-y divide-border rounded-md border border-border bg-surface">
                    {data.unhealthy_servers.map((s) => (
                      <li key={s.id} className="flex items-start justify-between gap-3 px-3 py-2">
                        <div className="min-w-0">
                          <Link href={`/mcp-servers?server=${s.id}`} className="text-sm font-medium hover:underline">
                            {s.name}
                          </Link>
                          {s.status_message ? <p className="truncate text-xs text-fg-muted">{s.status_message}</p> : null}
                        </div>
                        <StatusIndicator kind="server" value={s.status} />
                      </li>
                    ))}
                  </ul>
                )}
              </Section>

              <Section title="Next scheduled runs">
                {data.next_runs.length === 0 ? (
                  <p className="text-sm text-fg-muted">No active schedules.</p>
                ) : (
                  <ul className="flex flex-col divide-y divide-border rounded-md border border-border bg-surface">
                    {data.next_runs.map((s) => (
                      <li key={s.id} className="px-3 py-2">
                        <p className="text-sm font-medium">{s.name}</p>
                        <p className="text-xs text-fg-muted">
                          {s.pipeline_name} · {dateTime(s.next_run_at)}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>

              <Section title="Recent failures">
                {data.recent_failures.length === 0 ? (
                  <p className="text-sm text-fg-muted">No failures in the last 24 hours.</p>
                ) : (
                  <ul className="flex flex-col divide-y divide-border rounded-md border border-border bg-surface">
                    {data.recent_failures.map((e) => (
                      <li key={e.id} className="px-3 py-2">
                        <Link href={`/executions/${e.id}`} className="text-sm font-medium hover:underline">
                          {e.pipeline_name} <span className="font-mono text-xs text-fg-muted">{shortId(e.id)}</span>
                        </Link>
                        <p className="line-clamp-2 text-xs text-danger">{String((e.error as { message?: string } | null)?.message ?? "Failed")}</p>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>
            </div>
          </div>
        </>
      )}
    </PageContainer>
  );
}
