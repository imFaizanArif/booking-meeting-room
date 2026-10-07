"use client";

import { MoreHorizontal, Pencil, Plug, PlugZap, Plus, RefreshCw, ScanSearch, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger, Tooltip } from "@/components/ui/menus";
import { ConfirmDialog, Modal } from "@/components/ui/overlay";
import { PageHeader } from "@/components/ui/page";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status";
import { Gate } from "@/components/ui-extra/gate";
import { canOperate } from "@/features/auth/queries";
import type { Schemas } from "@/lib/api/client";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useDeleteServer, useDiscoverTools, useReconnectServer, useTestServer } from "./mutations";
import { transportLabel, useServers, type Server } from "./queries";
import { ServerDrawer } from "./server-drawer";

type Discovery = Schemas["DiscoveryOut"];
type Busy = "test" | "discover" | "reconnect";

function DiscoveryList({ label, names, tone }: { label: string; names: string[]; tone?: "danger" | "warn" }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium">{label}</span>
        <Badge tone={names.length ? (tone ?? "neutral") : "neutral"} className="tabular">
          {names.length}
        </Badge>
      </div>
      {names.length ? (
        <ul className="flex flex-wrap gap-1">
          {names.map((n) => (
            <li key={n} className="rounded-sm border border-border bg-subtle px-1.5 font-mono text-2xs leading-5">
              {n}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function DiscoveryModal({ result, server, onClose }: { result: Discovery | null; server: Server | null; onClose: () => void }) {
  return (
    <Modal
      open={!!result}
      onOpenChange={(o) => !o && onClose()}
      title={result?.ok ? `Discovered tools on ${server?.name ?? "server"}` : `Discovery failed on ${server?.name ?? "server"}`}
      description={result?.message}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          {result?.ok ? (
            <Button variant="primary" asChild>
              <Link href="/tools">Review tools</Link>
            </Button>
          ) : null}
        </>
      }
    >
      {result?.ok ? (
        <div className="flex flex-col gap-3">
          <DiscoveryList label="Added" names={result.added} />
          <DiscoveryList label="Updated" names={result.updated} />
          <DiscoveryList label="Schema changed" names={result.schema_changed} tone="warn" />
          <DiscoveryList label="Stale (no longer on the server)" names={result.stale} tone="danger" />
          {result.added.length ? <p className="text-xs text-fg-muted">New tools start disabled. Enable them on the Tools page.</p> : null}
        </div>
      ) : (
        <p className="text-sm text-fg-muted">Check the server&apos;s connection settings, then run discovery again.</p>
      )}
    </Modal>
  );
}

export function ServersView({ role }: { role: string | undefined }) {
  const { data, isPending, error, refetch } = useServers();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const paramId = params.get("server");

  const isOwner = role === "owner";
  const operate = canOperate(role);
  const [creating, setCreating] = React.useState(false);
  const [deleting, setDeleting] = React.useState<Server | null>(null);
  const [busy, setBusy] = React.useState<Record<string, Busy | undefined>>({});
  const [discovery, setDiscovery] = React.useState<{ server: Server; result: Discovery } | null>(null);
  const test = useTestServer();
  const reconnect = useReconnectServer();
  const discover = useDiscoverTools();
  const del = useDeleteServer();

  const editing = paramId ? (data?.find((s) => s.id === paramId) ?? null) : null;
  const drawerOpen = creating || !!editing;

  function setParam(id: string | null) {
    const next = new URLSearchParams(params.toString());
    if (id) next.set("server", id);
    else next.delete("server");
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  // A ?server= link to a deleted server: say so once and drop the param.
  const missingParam = !!paramId && !!data && !data.some((s) => s.id === paramId);
  React.useEffect(() => {
    if (!missingParam) return;
    toast.error("That MCP server no longer exists.");
    const next = new URLSearchParams(window.location.search);
    next.delete("server");
    router.replace(next.toString() ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  }, [missingParam, pathname, router]);

  function run(server: Server, kind: Busy) {
    setBusy((b) => ({ ...b, [server.id]: kind }));
    const done = () => setBusy((b) => ({ ...b, [server.id]: undefined }));
    if (kind === "discover") {
      discover.mutate(server.id, { onSuccess: (result) => setDiscovery({ server, result }), onSettled: done });
      return;
    }
    const m = kind === "test" ? test : reconnect;
    m.mutate(server.id, {
      onSuccess: (r) => {
        const title = kind === "test" ? (r.ok ? `${server.name}: connection works` : `${server.name}: connection failed`) : r.ok ? `${server.name} reconnected` : `${server.name} did not reconnect`;
        if (r.ok) toast.success(title, { description: r.message || undefined });
        else toast.error(title, { description: r.message || undefined });
      },
      onSettled: done,
    });
  }

  const add = (
    <Gate allowed={operate} reason="Viewers cannot add MCP servers.">
      <Button size="sm" variant="primary" onClick={() => setCreating(true)}>
        <Plus /> Add server
      </Button>
    </Gate>
  );

  return (
    <>
      <PageHeader
        title="MCP servers"
        description="Model Context Protocol servers that provide tools to agents. Status updates live."
        actions={data?.length ? add : undefined}
      />
      {isPending ? (
        <LoadingState rows={5} />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={Plug}
          title="No MCP servers yet"
          body="Connect a server over Streamable HTTP, or run one locally over stdio, then discover its tools."
          action={add}
        />
      ) : (
        <DataTable
          rows={data}
          getRowId={(s) => s.id}
          onRowClick={(s) => setParam(s.id)}
          searchText={(s) => `${s.name} ${s.slug} ${s.url ?? ""} ${s.command ?? ""}`}
          searchPlaceholder="Filter servers"
          initialSort={{ id: "name", desc: false }}
          rowClassName={(s) => cn(!s.is_active && "[&>td:not(:last-child)]:text-fg-muted")}
          columns={[
            {
              id: "name",
              header: "Server",
              sortValue: (s) => s.name.toLowerCase(),
              cell: (s) => (
                <div className="flex min-w-0 flex-col">
                  <span className="flex items-center gap-1.5 font-medium">
                    {s.name}
                    {!s.is_active ? <Badge tone="neutral">Inactive</Badge> : null}
                  </span>
                  <span className="font-mono text-xs text-fg-muted">{s.slug}</span>
                </div>
              ),
            },
            {
              id: "status",
              header: "Status",
              sortValue: (s) => s.status,
              cell: (s) => (
                <div className="flex min-w-0 max-w-[280px] flex-col">
                  <StatusIndicator kind="server" value={s.status} />
                  {s.status_message ? (
                    <Tooltip content={s.status_message}>
                      <span className="truncate text-xs text-fg-muted">{s.status_message}</span>
                    </Tooltip>
                  ) : null}
                </div>
              ),
            },
            {
              id: "transport",
              header: "Transport",
              sortValue: (s) => s.transport,
              cell: (s) => <Badge tone="outline">{transportLabel(s.transport)}</Badge>,
            },
            {
              id: "target",
              header: "Endpoint",
              cell: (s) => {
                const text = s.transport === "stdio" ? [s.command, ...s.args].join(" ") : (s.url ?? "");
                return (
                  <span className="block max-w-[260px] truncate font-mono text-xs text-fg-muted" title={text}>
                    {text || "—"}
                  </span>
                );
              },
            },
            {
              id: "tools",
              header: "Tools",
              align: "right",
              sortValue: (s) => s.tool_count,
              cell: (s) =>
                s.tool_count === 0 ? (
                  <span className="text-xs text-fg-subtle">None found</span>
                ) : (
                  <Link
                    href="/tools"
                    onClick={(e) => e.stopPropagation()}
                    className="whitespace-nowrap hover:underline"
                    aria-label={`${s.enabled_tool_count} of ${s.tool_count} tools enabled on ${s.name}`}
                  >
                    {s.enabled_tool_count}
                    <span className="text-fg-subtle"> / {s.tool_count} enabled</span>
                  </Link>
                ),
            },
            {
              id: "connected",
              header: "Last connected",
              align: "right",
              sortValue: (s) => s.last_connected_at ?? "",
              cell: (s) => <span className="whitespace-nowrap text-fg-muted">{s.last_connected_at ? relativeTime(s.last_connected_at) : "Never"}</span>,
            },
            {
              id: "actions",
              header: <span className="sr-only">Actions</span>,
              align: "right",
              cell: (s) => {
                const b = busy[s.id];
                return (
                  <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
                    <Gate allowed={operate} reason="Viewers cannot run discovery.">
                      <Button size="sm" variant="ghost" loading={b === "discover"} disabled={!!b} onClick={() => run(s, "discover")} aria-label={`Discover tools on ${s.name}`}>
                        {b === "discover" ? null : <ScanSearch />}
                        Discover
                      </Button>
                    </Gate>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button size="icon" variant="ghost" aria-label={`More actions for ${s.name}`} aria-busy={!!b || undefined}>
                          <MoreHorizontal />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        <DropdownMenuItem disabled={!operate || !!b} onSelect={() => run(s, "test")}>
                          <PlugZap /> {b === "test" ? "Testing connection…" : "Test connection"}
                        </DropdownMenuItem>
                        <DropdownMenuItem disabled={!operate || !!b} onSelect={() => run(s, "reconnect")}>
                          <RefreshCw /> {b === "reconnect" ? "Reconnecting…" : "Reconnect"}
                        </DropdownMenuItem>
                        <DropdownMenuItem onSelect={() => setParam(s.id)}>
                          <Pencil /> {operate ? "Edit server" : "View settings"}
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem tone="danger" disabled={!isOwner} onSelect={() => setDeleting(s)}>
                          <Trash2 /> Delete server
                        </DropdownMenuItem>
                        {!isOwner ? <p className="px-2 py-1 text-2xs text-fg-subtle">Only owners can delete servers.</p> : null}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                );
              },
            },
          ]}
        />
      )}

      <ServerDrawer
        open={drawerOpen}
        onOpenChange={(o) => {
          if (o) return;
          setCreating(false);
          if (paramId) setParam(null);
        }}
        server={creating ? null : editing}
        role={role}
      />

      <DiscoveryModal result={discovery?.result ?? null} server={discovery?.server ?? null} onClose={() => setDiscovery(null)} />

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete ${deleting?.name ?? "server"}?`}
        body={
          <>
            This disconnects the server, deletes its stored secrets and removes its {deleting?.tool_count ?? 0}{" "}
            {deleting?.tool_count === 1 ? "tool" : "tools"}. Agent nodes that use those tools will no longer be able to call them.
          </>
        }
        confirmLabel="Delete server"
        tone="danger"
        loading={del.isPending}
        onConfirm={() =>
          deleting &&
          del.mutate(deleting.id, {
            onSuccess: () => {
              toast.success(`Deleted ${deleting.name}`);
              setDeleting(null);
            },
          })
        }
      />
    </>
  );
}
