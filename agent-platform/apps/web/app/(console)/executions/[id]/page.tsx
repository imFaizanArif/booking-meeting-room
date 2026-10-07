"use client";

import { useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, Ban, Pause, Play, RefreshCw, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { PageContainer } from "@/components/shell/page-container";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { JsonViewer } from "@/components/ui/json-viewer";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/menus";
import { ConfirmDialog, Drawer } from "@/components/ui/overlay";
import { DescriptionList, PageHeader, Panel, Section } from "@/components/ui/page";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status";
import { canOperate, useMe } from "@/features/auth/queries";
import { executionKeys, useControlExecution, useExecution, useExecutionEvents, useRestartExecution } from "@/features/executions/queries";
import { StatusGraph } from "@/features/executions/status-graph";
import { Timeline } from "@/features/executions/timeline";
import { type StreamState, useExecutionStream } from "@/features/realtime/use-stream";
import type { Schemas } from "@/lib/api/client";
import { compact, dateTime, duration, ms, relativeTime, shortId, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

type ToolCall = Schemas["ToolCallOut"];
type Event = Schemas["ExecutionEventOut"];

const TERMINAL = new Set(["completed", "cancelled"]);

function LiveBadge({ state, terminal }: { state: StreamState; terminal: boolean }) {
  if (terminal) return <span className="text-xs text-fg-subtle">Finished</span>;
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-xs", state === "live" ? "text-info" : "text-fg-subtle")}>
      <span className={cn("size-1.5 rounded-full", state === "live" ? "anim-pulse bg-info" : "bg-fg-subtle")} aria-hidden />
      {state === "live" ? "Live" : state === "reconnecting" ? "Reconnecting…" : "Connecting…"}
    </span>
  );
}

export default function ExecutionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const qc = useQueryClient();
  const me = useMe();
  const detail = useExecution(id);
  const history = useExecutionEvents(id);
  const control = useControlExecution(id);
  const restart = useRestartExecution(id);
  const [selectedNode, setSelectedNode] = React.useState<string | null>(null);
  const [toolCall, setToolCall] = React.useState<ToolCall | null>(null);
  const [confirm, setConfirm] = React.useState<null | "cancel">(null);
  const [tab, setTab] = React.useState("overview");

  const refresh = React.useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const onEvent = React.useCallback(
    (event: Event) => {
      qc.setQueryData<Event[]>(executionKeys.events(id), (old) => {
        const list = old ?? [];
        return list.some((e) => e.seq === event.seq) ? list : [...list, event].sort((a, b) => a.seq - b.seq);
      });
      clearTimeout(refresh.current);
      refresh.current = setTimeout(() => void qc.invalidateQueries({ queryKey: executionKeys.detail(id) }), 250);
    },
    [qc, id],
  );
  const status = detail.data?.execution.status;
  const terminal = !!status && TERMINAL.has(status);
  const stream = useExecutionStream(history.isSuccess ? id : undefined, onEvent, !terminal);

  if (detail.isPending) {
    return (
      <PageContainer>
        <LoadingState rows={10} />
      </PageContainer>
    );
  }
  if (detail.error) {
    return (
      <PageContainer>
        <ErrorState error={detail.error} onRetry={() => void detail.refetch()} />
      </PageContainer>
    );
  }

  const { execution, nodes, tool_calls: calls, usage, approvals, graph, snapshot } = detail.data;
  const operator = canOperate(me.data?.role);
  const pendingApprovals = approvals.filter((a) => a.status === "pending");
  const waitingNodes = new Set(pendingApprovals.map((a) => a.node_id));
  const node = selectedNode ? nodes.find((n) => n.node_id === selectedNode) : undefined;
  const graphNode = selectedNode ? graph.nodes.find((n) => n.id === selectedNode) : undefined;
  const events = history.data ?? [];

  async function act(action: "pause" | "resume" | "cancel" | "retry", message: string) {
    await control.mutateAsync(action);
    toast.success(message);
    setConfirm(null);
  }

  const canPause = ["queued", "running", "resuming", "waiting_for_tool"].includes(execution.status) && !execution.pause_requested;
  const canResume = execution.status === "paused";
  const canRetry = execution.status === "failed";
  const canCancel = !TERMINAL.has(execution.status) && !execution.cancel_requested;
  const error = execution.error as { message?: string; code?: string } | null;

  return (
    <PageContainer full className="max-w-none">
      <PageHeader
        title={
          <span className="flex items-center gap-3">
            {execution.pipeline_name}
            <span className="font-mono text-sm font-normal text-fg-muted">{shortId(execution.id)}</span>
          </span>
        }
        meta={
          <>
            <StatusIndicator kind="execution" value={execution.status} />
            <LiveBadge state={stream.state} terminal={terminal} />
            <span>
              v{execution.pipeline_version} ·{" "}
              <Link href={`/pipelines/${execution.pipeline_id}`} className="hover:underline">
                open pipeline
              </Link>
            </span>
            <span className="capitalize">{execution.trigger}</span>
            <span title={dateTime(execution.created_at)}>Started {relativeTime(execution.started_at ?? execution.created_at)}</span>
            <span className="tabular">{duration(execution.started_at, execution.finished_at)}</span>
            <span className="tabular">{compact(execution.total_tokens)} tokens · {usd(execution.estimated_cost)}</span>
            {execution.restarted_from_id ? (
              <Link href={`/executions/${execution.restarted_from_id}`} className="hover:underline">
                Restart of {shortId(execution.restarted_from_id)}
              </Link>
            ) : null}
          </>
        }
        actions={
          operator ? (
            <>
              {canPause ? (
                <Button size="sm" onClick={() => void act("pause", "Pausing after the current step.")} loading={control.isPending}>
                  <Pause /> Pause
                </Button>
              ) : null}
              {canResume ? (
                <Button size="sm" variant="primary" onClick={() => void act("resume", "Resuming.")} loading={control.isPending}>
                  <Play /> Resume
                </Button>
              ) : null}
              {canRetry ? (
                <Button size="sm" variant="primary" onClick={() => void act("retry", "Retrying from the failed step.")} loading={control.isPending}>
                  <RotateCcw /> Retry failed step
                </Button>
              ) : null}
              <Button
                size="sm"
                onClick={async () => {
                  const next = await restart.mutateAsync();
                  router.push(`/executions/${next.id}`);
                }}
                loading={restart.isPending}
              >
                <RefreshCw /> Run again
              </Button>
              {canCancel ? (
                <Button size="sm" variant="danger-outline" onClick={() => setConfirm("cancel")}>
                  <Ban /> Cancel
                </Button>
              ) : null}
            </>
          ) : null
        }
      />

      {pendingApprovals.length ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-md bg-warn-bg px-4 py-2.5 text-sm text-warn">
          <span>
            Paused for review: {pendingApprovals.map((a) => a.title).join(", ")}
          </span>
          <Link href={`/approvals/${pendingApprovals[0]!.id}`} className="inline-flex items-center gap-1 font-medium hover:underline">
            Review now <ArrowUpRight className="size-3.5" />
          </Link>
        </div>
      ) : null}
      {error && execution.status === "failed" ? (
        <div role="alert" className="rounded-md bg-danger-bg px-4 py-2.5 text-sm text-danger">
          <span className="font-mono text-xs">{error.code}</span> {error.message}
        </div>
      ) : null}
      {execution.pause_requested && execution.status !== "paused" ? (
        <p className="text-sm text-fg-muted">Pause requested. The execution stops after the step in progress.</p>
      ) : null}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="events">Live log <Badge>{events.length}</Badge></TabsTrigger>
          <TabsTrigger value="tools">Tool calls <Badge>{calls.length}</Badge></TabsTrigger>
          <TabsTrigger value="llm">LLM calls <Badge>{usage.length}</Badge></TabsTrigger>
          <TabsTrigger value="approvals">Approvals <Badge>{approvals.length}</Badge></TabsTrigger>
          <TabsTrigger value="data">Input &amp; output</TabsTrigger>
          <TabsTrigger value="snapshot">Snapshot</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="pt-4">
          <Panel className="h-[440px] overflow-hidden">
            <StatusGraph graph={graph} nodes={nodes} waitingNodeIds={waitingNodes} selected={selectedNode} onSelect={setSelectedNode} />
          </Panel>
          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
            <Panel className="scrollbar-thin max-h-[520px] overflow-y-auto p-4">
              {node && graphNode ? (
                <div className="flex flex-col gap-4">
                  <div>
                    <p className="text-xs text-fg-muted">{graphNode.type.replace("_", " ")}</p>
                    <h3 className="text-base font-semibold">{graphNode.name}</h3>
                  </div>
                  <DescriptionList
                    className="text-xs"
                    items={[
                      { label: "Status", value: <StatusIndicator kind="node" value={node.status} /> },
                      { label: "Attempts", value: node.attempts },
                      { label: "Started", value: dateTime(node.started_at) },
                      { label: "Duration", value: duration(node.started_at, node.finished_at) },
                    ]}
                  />
                  {node.error ? <JsonViewer value={node.error} defaultOpen={1} className="border-danger/30" /> : null}
                  {node.input_summary ? (
                    <Section title="Input">
                      <JsonViewer value={node.input_summary.value ?? node.input_summary} defaultOpen={1} />
                    </Section>
                  ) : null}
                  {node.output_summary ? (
                    <Section title="Output">
                      <JsonViewer value={node.output_summary.value ?? node.output_summary} defaultOpen={2} />
                    </Section>
                  ) : null}
                  {calls.some((c) => c.node_id === node.node_id) ? (
                    <Section title="Tool calls">
                      <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
                        {calls.filter((c) => c.node_id === node.node_id).map((c) => (
                          <li key={c.id}>
                            <button type="button" onClick={() => setToolCall(c)} className="flex w-full items-center justify-between gap-2 px-2.5 py-1.5 text-left hover:bg-subtle">
                              <span className="truncate font-mono text-xs">{c.namespaced_name}</span>
                              <StatusIndicator kind="toolCall" value={c.status} />
                            </button>
                          </li>
                        ))}
                      </ul>
                    </Section>
                  ) : null}
                </div>
              ) : selectedNode && graphNode ? (
                <p className="text-sm text-fg-muted">{graphNode.name} has not run in this execution.</p>
              ) : (
                <div className="flex flex-col gap-1">
                  <h3 className="text-sm font-semibold">Node details</h3>
                  <p className="text-sm text-fg-muted">Select a node in the graph to see its input, output, errors and tool calls.</p>
                </div>
              )}
            </Panel>
            <Panel className="scrollbar-thin max-h-[520px] overflow-y-auto">
              <h3 className="border-b border-border px-4 py-2.5 text-sm font-semibold">Recent activity</h3>
              <Timeline compact events={events.slice(-16).reverse()} onSelectNode={setSelectedNode} />
            </Panel>
          </div>
        </TabsContent>

        <TabsContent value="events" className="pt-4">
          <Panel className="scrollbar-thin max-h-[70vh] overflow-y-auto">
            {history.isPending ? <LoadingState rows={8} className="p-3" /> : <Timeline events={events} onSelectNode={(n) => { setSelectedNode(n); setTab("overview"); }} />}
          </Panel>
        </TabsContent>

        <TabsContent value="tools" className="pt-4">
          <DataTable
            rows={calls}
            getRowId={(c) => c.id}
            onRowClick={setToolCall}
            searchText={(c) => `${c.namespaced_name} ${c.node_id} ${c.status}`}
            searchPlaceholder="Filter tool calls"
            empty="No tool calls in this execution."
            columns={[
              { id: "seq", header: "#", cell: (c) => <span className="tabular text-fg-subtle">{c.call_seq}</span> },
              { id: "tool", header: "Tool", cell: (c) => <span className="font-mono text-xs">{c.namespaced_name}</span> },
              { id: "node", header: "Node", cell: (c) => <span className="font-mono text-xs text-fg-muted">{c.node_id}</span> },
              { id: "status", header: "Status", cell: (c) => <StatusIndicator kind="toolCall" value={c.status} /> },
              { id: "policy", header: "Policy", cell: (c) => <span className="text-xs text-fg-muted">{String((c.policy_decision as { decision?: string } | null)?.decision ?? "—")}</span> },
              { id: "attempt", header: "Attempt", align: "right", cell: (c) => c.attempt },
              { id: "duration", header: "Duration", align: "right", cell: (c) => ms(c.duration_ms) },
            ]}
          />
        </TabsContent>

        <TabsContent value="llm" className="pt-4">
          <DataTable
            rows={usage}
            getRowId={(u) => u.id}
            empty="No model calls yet."
            columns={[
              { id: "node", header: "Node", cell: (u) => <span className="font-mono text-xs">{u.node_id}</span> },
              { id: "model", header: "Model", cell: (u) => <span>{u.model} <span className="text-xs text-fg-subtle">{u.provider}</span></span> },
              { id: "summary", header: "Output", cell: (u) => <span className="line-clamp-1 max-w-md text-xs text-fg-muted" title={u.summary ?? ""}>{u.summary}</span> },
              { id: "in", header: "In", align: "right", cell: (u) => compact(u.input_tokens) },
              { id: "out", header: "Out", align: "right", cell: (u) => compact(u.output_tokens) },
              { id: "cost", header: "Cost", align: "right", cell: (u) => usd(u.estimated_cost) },
              { id: "latency", header: "Latency", align: "right", cell: (u) => ms(u.latency_ms) },
            ]}
          />
        </TabsContent>

        <TabsContent value="approvals" className="pt-4">
          <DataTable
            rows={approvals}
            getRowId={(a) => a.id}
            onRowClick={(a) => router.push(`/approvals/${a.id}?filter=all`)}
            empty="This execution never paused for review."
            columns={[
              { id: "title", header: "Action", cell: (a) => <span className="font-medium">{a.title}</span> },
              { id: "kind", header: "Kind", cell: (a) => <span className="text-xs text-fg-muted">{a.kind.replace("_", " ")}</span> },
              { id: "status", header: "Status", cell: (a) => <StatusIndicator kind="approval" value={a.status} /> },
              { id: "decision", header: "Decision", cell: (a) => <span className="text-xs text-fg-muted">{a.decision ?? "—"}{a.decided_by_email ? ` · ${a.decided_by_email}` : ""}</span> },
              { id: "when", header: "Requested", align: "right", cell: (a) => <span className="text-fg-muted">{relativeTime(a.created_at)}</span> },
            ]}
          />
        </TabsContent>

        <TabsContent value="data" className="grid grid-cols-1 gap-6 pt-4 lg:grid-cols-2">
          <Section title="Input">
            <JsonViewer value={execution.input} defaultOpen={3} />
          </Section>
          <Section title="Output">{execution.output ? <JsonViewer value={execution.output} defaultOpen={3} /> : <p className="text-sm text-fg-muted">No output yet.</p>}</Section>
        </TabsContent>

        <TabsContent value="snapshot" className="pt-4">
          <Section title="Configuration snapshot" description="The exact configuration this execution runs with. Later edits to models, prompts or tools do not change it. Secrets appear only as references.">
            <JsonViewer value={snapshot} defaultOpen={1} className="max-h-[70vh]" />
          </Section>
        </TabsContent>
      </Tabs>

      <Drawer open={!!toolCall} onOpenChange={(o) => !o && setToolCall(null)} title={toolCall?.namespaced_name ?? ""} description={toolCall ? `Node ${toolCall.node_id} · call ${toolCall.call_seq}` : undefined}>
        {toolCall ? (
          <div className="flex flex-col gap-5">
            <DescriptionList
              className="text-xs"
              items={[
                { label: "Status", value: <StatusIndicator kind="toolCall" value={toolCall.status} /> },
                { label: "Idempotency key", value: <span className="font-mono">{toolCall.idempotency_key}</span> },
                { label: "Read-only", value: toolCall.is_read_only ? "Yes (safe to retry)" : "No (never retried automatically)" },
                { label: "Attempts", value: toolCall.attempt },
                { label: "Duration", value: ms(toolCall.duration_ms) },
                { label: "Started", value: dateTime(toolCall.started_at) },
              ]}
            />
            <Section title="Arguments"><JsonViewer value={toolCall.arguments} defaultOpen={3} /></Section>
            {toolCall.policy_decision ? <Section title="Policy decision"><JsonViewer value={toolCall.policy_decision} /></Section> : null}
            {toolCall.result ? <Section title="Result"><JsonViewer value={toolCall.result} defaultOpen={2} /></Section> : null}
            {toolCall.error ? <Section title="Error"><JsonViewer value={toolCall.error} /></Section> : null}
          </div>
        ) : null}
      </Drawer>

      <ConfirmDialog
        open={confirm === "cancel"}
        onOpenChange={(o) => setConfirm(o ? "cancel" : null)}
        title="Cancel this execution"
        body="Steps in progress finish their current tool call, then the execution stops. Pending approvals expire. This cannot be undone; you can run it again later."
        confirmLabel="Cancel execution"
        tone="danger"
        loading={control.isPending}
        onConfirm={() => void act("cancel", "Cancelling.")}
      />
    </PageContainer>
  );
}
