"use client";

import { MoreHorizontal, Pencil, Plus, PlugZap, Server, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger, Tooltip } from "@/components/ui/menus";
import { ConfirmDialog } from "@/components/ui/overlay";
import { Section } from "@/components/ui/page";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Switch } from "@/components/ui/toggles";
import { Gate } from "@/components/ui-extra/gate";
import { SecretState } from "@/components/ui-extra/secret-state";
import { canOperate } from "@/features/auth/queries";
import { ApiError } from "@/lib/api/client";
import { relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useDeleteProvider, useSetProviderActive, useTestProvider } from "./mutations";
import { ProviderDrawer } from "./provider-drawer";
import { providerTypeLabel, useProviders, type Provider } from "./queries";

export const OWNER_ONLY = "Only workspace owners can change providers and models.";

/** Last connection test: the fresh result while one is shown, otherwise the stored one. */
function TestResultCell({ provider, pending, fresh }: { provider: Provider; pending: boolean; fresh: { ok: boolean; message: string } | null }) {
  if (pending) return <span className="text-xs text-fg-muted">Testing…</span>;
  const ok = fresh ? fresh.ok : provider.last_test_ok;
  const message = fresh ? fresh.message : provider.last_test_message;
  if (ok == null) return <span className="text-xs text-fg-subtle">Not tested</span>;
  const content = (
    <span className="inline-flex min-w-0 max-w-[260px] items-center gap-2">
      <Badge tone={ok ? "ok" : "danger"}>{ok ? "Connected" : "Failed"}</Badge>
      <span className="truncate text-xs text-fg-muted">{fresh ? "just now" : relativeTime(provider.last_test_at)}</span>
    </span>
  );
  return message ? (
    <Tooltip content={message}>
      <span tabIndex={0} className="inline-flex min-w-0 rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25">
        {content}
      </span>
    </Tooltip>
  ) : (
    content
  );
}

export function ProvidersSection({ role }: { role: string | undefined }) {
  const { data, isPending, error, refetch } = useProviders();
  const isOwner = role === "owner";
  const canTest = canOperate(role);
  const [editing, setEditing] = React.useState<Provider | null>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [deleting, setDeleting] = React.useState<Provider | null>(null);
  const setActive = useSetProviderActive();
  const del = useDeleteProvider();
  const test = useTestProvider();
  const [testing, setTesting] = React.useState<Set<string>>(new Set());
  const [fresh, setFresh] = React.useState<Record<string, { ok: boolean; message: string }>>({});

  function openEditor(p: Provider | null) {
    setEditing(p);
    setDrawerOpen(true);
  }

  function runTest(p: Provider) {
    setTesting((s) => new Set(s).add(p.id));
    test.mutate(p.id, {
      onSuccess: (r) => setFresh((f) => ({ ...f, [p.id]: { ok: r.ok, message: r.message } })),
      onError: (err) =>
        setFresh((f) => ({ ...f, [p.id]: { ok: false, message: err instanceof ApiError ? err.message : "The test request failed." } })),
      onSettled: () =>
        setTesting((s) => {
          const next = new Set(s);
          next.delete(p.id);
          return next;
        }),
    });
  }

  const add = (
    <Gate allowed={isOwner} reason={OWNER_ONLY}>
      <Button size="sm" variant="primary" onClick={() => openEditor(null)}>
        <Plus /> Add provider
      </Button>
    </Gate>
  );

  return (
    <Section title="Providers" description="API connections used by LLM nodes. Keys are write-only." actions={data?.length ? add : undefined}>
      {isPending ? (
        <LoadingState rows={4} />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : data.length === 0 ? (
        <EmptyState
          icon={Server}
          title="No providers yet"
          body="Add an OpenAI, Anthropic, Gemini or Ollama connection so pipelines can call a model."
          action={add}
        />
      ) : (
        <DataTable
          rows={data}
          getRowId={(p) => p.id}
          initialSort={{ id: "name", desc: false }}
          columns={[
            {
              id: "name",
              header: "Name",
              sortValue: (p) => p.name.toLowerCase(),
              cell: (p) => (
                <div className="flex min-w-0 flex-col">
                  <span className="font-medium">{p.name}</span>
                  <span className="text-xs text-fg-muted">
                    {p.model_count} {p.model_count === 1 ? "model" : "models"}
                  </span>
                </div>
              ),
            },
            { id: "type", header: "Type", sortValue: (p) => p.provider_type, cell: (p) => <Badge tone="outline">{providerTypeLabel(p.provider_type)}</Badge> },
            {
              id: "url",
              header: "Base URL",
              cell: (p) =>
                p.base_url ? (
                  <span className="block max-w-[240px] truncate font-mono text-xs text-fg-muted" title={p.base_url}>
                    {p.base_url}
                  </span>
                ) : (
                  <span className="text-xs text-fg-subtle">Default</span>
                ),
            },
            { id: "key", header: "API key", cell: (p) => <SecretState state={p.api_key} setLabel="Key set" unsetLabel="No key" /> },
            {
              id: "test",
              header: "Last test",
              cell: (p) => <TestResultCell provider={p} pending={testing.has(p.id)} fresh={fresh[p.id] ?? null} />,
            },
            {
              id: "active",
              header: "Active",
              cell: (p) => (
                <Gate allowed={isOwner} reason={OWNER_ONLY}>
                  <Switch
                    checked={p.is_active}
                    onCheckedChange={(is_active) => setActive.mutate({ id: p.id, is_active })}
                    aria-label={`${p.name} active`}
                  />
                </Gate>
              ),
            },
            {
              id: "actions",
              header: <span className="sr-only">Actions</span>,
              align: "right",
              cell: (p) => (
                <div className="flex items-center justify-end gap-1">
                  <Gate allowed={canTest} reason="Viewers cannot run connection tests.">
                    <Button size="sm" variant="ghost" loading={testing.has(p.id)} onClick={() => runTest(p)} aria-label={`Test connection to ${p.name}`}>
                      {testing.has(p.id) ? null : <PlugZap />}
                      Test
                    </Button>
                  </Gate>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button size="icon" variant="ghost" aria-label={`More actions for ${p.name}`}>
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent>
                      <DropdownMenuItem disabled={!isOwner} onSelect={() => openEditor(p)}>
                        <Pencil /> Edit provider
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem tone="danger" disabled={!isOwner} onSelect={() => setDeleting(p)}>
                        <Trash2 /> Delete provider
                      </DropdownMenuItem>
                      {!isOwner ? <p className="px-2 py-1 text-2xs text-fg-subtle">{OWNER_ONLY}</p> : null}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ),
            },
          ]}
          rowClassName={(p) => cn(!p.is_active && "[&>td:not(:last-child)]:text-fg-muted")}
        />
      )}

      <ProviderDrawer open={drawerOpen} onOpenChange={setDrawerOpen} provider={editing} />

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete ${deleting?.name ?? "provider"}?`}
        body={
          <>
            This removes the provider, its stored API key and its {deleting?.model_count ?? 0} registered{" "}
            {deleting?.model_count === 1 ? "model" : "models"}. Pipeline nodes that reference those models will need a different
            model.
          </>
        }
        confirmLabel="Delete provider"
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
    </Section>
  );
}
