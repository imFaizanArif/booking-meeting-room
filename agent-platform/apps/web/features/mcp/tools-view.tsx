"use client";

import { Search, ShieldCheck, ShieldOff, ToggleLeft, ToggleRight, Wrench, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/menus";
import { PageHeader } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status";
import { Gate } from "@/components/ui-extra/gate";
import { canOperate } from "@/features/auth/queries";
import type { Schemas } from "@/lib/api/client";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useBulkUpdateTools } from "./mutations";
import { useServers, useTools, type Server, type Tool } from "./queries";
import { RiskSelect, ToolSwitch } from "./tool-controls";
import { ToolDrawer } from "./tool-drawer";

export type ToolFilter = "all" | "enabled" | "approval" | "stale";

const FILTERS: { value: ToolFilter; label: string }[] = [
  { value: "all", label: "All tools" },
  { value: "enabled", label: "Only enabled" },
  { value: "approval", label: "Only needs approval" },
  { value: "stale", label: "Only stale" },
];

export function filterTools(tools: Tool[], query: string, filter: ToolFilter): Tool[] {
  const q = query.trim().toLowerCase();
  return tools.filter((t) => {
    if (filter === "enabled" && !t.is_enabled) return false;
    if (filter === "approval" && !t.requires_approval) return false;
    if (filter === "stale" && !t.is_stale) return false;
    if (!q) return true;
    return `${t.name} ${t.namespaced_name} ${t.title ?? ""} ${t.description ?? ""} ${t.server_name}`.toLowerCase().includes(q);
  });
}

interface Group {
  serverId: string;
  name: string;
  slug: string;
  server: Server | undefined;
  tools: Tool[];
}

function groupByServer(tools: Tool[], servers: Server[] | undefined): Group[] {
  const map = new Map<string, Group>();
  for (const t of tools) {
    let g = map.get(t.server_id);
    if (!g) {
      g = { serverId: t.server_id, name: t.server_name, slug: t.server_slug, server: servers?.find((s) => s.id === t.server_id), tools: [] };
      map.set(t.server_id, g);
    }
    g.tools.push(t);
  }
  return [...map.values()].sort((a, b) => a.name.localeCompare(b.name));
}

type BulkAction = { label: string; done: string; patch: Schemas["MCPToolPatch"]; icon: React.ReactNode };

const BULK: BulkAction[] = [
  { label: "Enable", done: "Enabled", patch: { is_enabled: true }, icon: <ToggleRight /> },
  { label: "Disable", done: "Disabled", patch: { is_enabled: false }, icon: <ToggleLeft /> },
  { label: "Require approval", done: "Approval now required for", patch: { requires_approval: true }, icon: <ShieldCheck /> },
  { label: "Don't require approval", done: "Approval no longer required for", patch: { requires_approval: false }, icon: <ShieldOff /> },
];

export function ToolsView({ role }: { role: string | undefined }) {
  const tools = useTools();
  const servers = useServers();
  const bulk = useBulkUpdateTools();
  const canEdit = canOperate(role);
  const [query, setQuery] = React.useState("");
  const [filter, setFilter] = React.useState<ToolFilter>("all");
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [openId, setOpenId] = React.useState<string | null>(null);

  const all = React.useMemo(() => tools.data ?? [], [tools.data]);
  const visible = React.useMemo(() => filterTools(all, query, filter), [all, query, filter]);
  const groups = React.useMemo(() => groupByServer(visible, servers.data), [visible, servers.data]);
  const openTool = openId ? (all.find((t) => t.id === openId) ?? null) : null;

  // Drop selections that disappeared (deleted server, refetch).
  const selectedIds = React.useMemo(() => [...selected].filter((id) => all.some((t) => t.id === id)), [selected, all]);
  const selectedStale = selectedIds.filter((id) => all.find((t) => t.id === id)?.is_stale).length;

  const counts = {
    total: all.length,
    enabled: all.filter((t) => t.is_enabled).length,
    approval: all.filter((t) => t.requires_approval).length,
    stale: all.filter((t) => t.is_stale).length,
  };

  function runBulk(action: BulkAction) {
    const ids = selectedIds;
    if (!ids.length) return;
    const skipped = action.patch.is_enabled ? selectedStale : 0;
    const n = ids.length - skipped;
    bulk.mutate(
      { ids, patch: action.patch },
      {
        onSuccess: () => {
          toast.success(`${action.done} ${n} ${n === 1 ? "tool" : "tools"}`, {
            description: skipped ? `${skipped} stale ${skipped === 1 ? "tool was" : "tools were"} skipped.` : undefined,
          });
          setSelected(new Set());
        },
      },
    );
  }

  const columns = [
    {
      id: "name",
      header: "Tool",
      sortValue: (t: Tool) => t.name,
      cell: (t: Tool) => (
        <div className="flex min-w-0 flex-col">
          <span className="flex items-center gap-1.5">
            <span className="font-mono text-xs font-medium text-fg">{t.name}</span>
            {t.is_stale ? <Badge tone="danger">Stale</Badge> : null}
          </span>
          <span className="truncate font-mono text-2xs text-fg-subtle">{t.namespaced_name}</span>
        </div>
      ),
    },
    {
      id: "description",
      header: "Description",
      className: "max-w-0 w-full",
      cell: (t: Tool) =>
        t.description ? (
          <Tooltip content={<span className="whitespace-pre-wrap">{t.description}</span>}>
            <span className="block truncate text-xs text-fg-muted">{t.description}</span>
          </Tooltip>
        ) : (
          <span className="text-xs text-fg-subtle">No description</span>
        ),
    },
    {
      id: "enabled",
      header: "Enabled",
      cell: (t: Tool) => (
        <div onClick={(e) => e.stopPropagation()}>
          <ToolSwitch tool={t} flag="is_enabled" canEdit={canEdit} />
        </div>
      ),
    },
    {
      id: "approval",
      header: "Approval",
      cell: (t: Tool) => (
        <div onClick={(e) => e.stopPropagation()}>
          <ToolSwitch tool={t} flag="requires_approval" canEdit={canEdit} />
        </div>
      ),
    },
    {
      id: "destructive",
      header: "Destructive",
      cell: (t: Tool) => (
        <div onClick={(e) => e.stopPropagation()}>
          <ToolSwitch tool={t} flag="is_destructive" canEdit={canEdit} />
        </div>
      ),
    },
    {
      id: "risk",
      header: "Risk",
      sortValue: (t: Tool) => ["low", "medium", "high", "critical"].indexOf(t.risk_level),
      cell: (t: Tool) => (
        <div onClick={(e) => e.stopPropagation()}>
          <RiskSelect tool={t} canEdit={canEdit} />
        </div>
      ),
    },
    {
      id: "discovered",
      header: "Discovered",
      align: "right" as const,
      sortValue: (t: Tool) => t.last_discovered_at ?? "",
      cell: (t: Tool) => <span className="whitespace-nowrap text-xs text-fg-muted">{relativeTime(t.last_discovered_at)}</span>,
    },
  ];

  const filtering = query.trim() !== "" || filter !== "all";

  return (
    <>
      <PageHeader
        title="Tools"
        description="Every tool discovered on your MCP servers, and the policy agents run them under. New tools start disabled."
        meta={
          tools.data ? (
            <>
              <span className="tabular">{counts.total} tools</span>
              <span className="tabular">{counts.enabled} enabled</span>
              <span className="tabular">{counts.approval} need approval</span>
              {counts.stale ? <span className="tabular text-danger">{counts.stale} stale</span> : null}
            </>
          ) : undefined
        }
      />

      {tools.isPending ? (
        <LoadingState rows={8} />
      ) : tools.error ? (
        <ErrorState error={tools.error} onRetry={() => void tools.refetch()} />
      ) : all.length === 0 ? (
        <EmptyState
          icon={Wrench}
          title="No tools discovered yet"
          body="Tools appear here after you run discovery on an MCP server."
          action={
            <Button size="sm" asChild>
              <Link href="/mcp-servers">Go to MCP servers</Link>
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-6">
          <div className="sticky top-0 z-10 -mx-1 flex min-h-9 flex-wrap items-center gap-2 bg-bg px-1 py-1">
            {selectedIds.length ? (
              <div role="toolbar" aria-label="Bulk actions" className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-xs font-medium tabular">{selectedIds.length} selected</span>
                {BULK.map((a) => (
                  <Gate key={a.label} allowed={canEdit} reason="Viewers cannot change tool policy.">
                    <Button size="sm" disabled={bulk.isPending} onClick={() => runBulk(a)}>
                      {a.icon}
                      {a.label}
                    </Button>
                  </Gate>
                ))}
                <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>
                  <X /> Clear selection
                </Button>
              </div>
            ) : (
              <>
                <div className="relative w-64 max-w-full">
                  <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" aria-hidden />
                  <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Filter tools" aria-label="Filter tools" className="h-7 pl-8 text-xs" />
                </div>
                <label htmlFor="tool-filter" className="sr-only">
                  Show
                </label>
                <div className="w-48">
                  <Select id="tool-filter" size="sm" value={filter} onValueChange={(v) => setFilter(v as ToolFilter)} options={FILTERS} />
                </div>
                {filtering ? (
                  <span className="text-xs text-fg-muted tabular">
                    {visible.length} of {all.length}
                  </span>
                ) : null}
              </>
            )}
          </div>

          {groups.length === 0 ? (
            <EmptyState
              title="No tools match"
              body="Try a different filter or search term."
              action={
                <Button
                  size="sm"
                  onClick={() => {
                    setQuery("");
                    setFilter("all");
                  }}
                >
                  Clear filters
                </Button>
              }
            />
          ) : (
            groups.map((g) => {
              const enabled = g.tools.filter((t) => t.is_enabled).length;
              return (
                <section key={g.serverId} className="flex flex-col gap-2" aria-labelledby={`grp-${g.serverId}`}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                      <h2 id={`grp-${g.serverId}`} className="text-sm font-semibold">
                        <Link href={`/mcp-servers?server=${g.serverId}`} className="hover:underline">
                          {g.name}
                        </Link>
                      </h2>
                      {g.server ? <StatusIndicator kind="server" value={g.server.status} /> : null}
                      {g.server && !g.server.is_active ? <Badge>Inactive</Badge> : null}
                    </div>
                    <span className="text-xs text-fg-muted tabular">
                      {enabled} of {g.tools.length} enabled
                    </span>
                  </div>
                  {g.server?.status_message && g.server.status !== "ready" ? <p className="-mt-1 text-xs text-fg-muted">{g.server.status_message}</p> : null}
                  <DataTable
                    rows={g.tools}
                    getRowId={(t) => t.id}
                    columns={columns}
                    selectable={canEdit}
                    selected={selected}
                    onSelectedChange={setSelected}
                    onRowClick={(t) => setOpenId(t.id)}
                    pageSize={100}
                    rowClassName={(t) => cn(t.is_stale && "[&_td]:text-fg-muted")}
                  />
                </section>
              );
            })
          )}
        </div>
      )}

      <ToolDrawer tool={openTool} onClose={() => setOpenId(null)} canEdit={canEdit} />
    </>
  );
}
