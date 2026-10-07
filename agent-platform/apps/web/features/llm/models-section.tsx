"use client";

import { Boxes, MoreHorizontal, Pencil, Plus, Star, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/menus";
import { ConfirmDialog } from "@/components/ui/overlay";
import { Section } from "@/components/ui/page";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Switch } from "@/components/ui/toggles";
import { Gate } from "@/components/ui-extra/gate";
import { compact } from "@/lib/format";
import { cn } from "@/lib/utils";

import { ModelDrawer } from "./model-drawer";
import { useDeleteModel, useSetDefaultModel, useSetModelActive } from "./mutations";
import { OWNER_ONLY } from "./providers-section";
import { useModels, useProviders, type Model } from "./queries";

/** "$4.00" for whole cents, more precision for sub-cent prices, "Free" for 0. */
export function pricePerMTok(value: string | number): string {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "Free";
  const digits = n < 0.01 ? 4 : n < 1 && Math.round(n * 1000) % 10 !== 0 ? 3 : 2;
  return `$${n.toFixed(digits)}`;
}

function Capability({ on, label }: { on: boolean; label: string }) {
  return on ? <Badge tone="neutral">{label}</Badge> : null;
}

export function ModelsSection({ role }: { role: string | undefined }) {
  const models = useModels();
  const providers = useProviders();
  const isOwner = role === "owner";
  const [editing, setEditing] = React.useState<Model | null>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [deleting, setDeleting] = React.useState<Model | null>(null);
  const setActive = useSetModelActive();
  const setDefault = useSetDefaultModel();
  const del = useDeleteModel();

  const providerList = providers.data ?? [];
  const noProviders = providers.isSuccess && providerList.length === 0;

  function openEditor(m: Model | null) {
    setEditing(m);
    setDrawerOpen(true);
  }

  const add = (
    <Gate allowed={isOwner && !noProviders} reason={noProviders ? "Add a provider first." : OWNER_ONLY}>
      <Button size="sm" variant={models.data?.length ? "secondary" : "primary"} onClick={() => openEditor(null)}>
        <Plus /> Add model
      </Button>
    </Gate>
  );

  const hasDefault = models.data?.some((m) => m.is_default);

  return (
    <Section
      title="Models"
      description={
        hasDefault || !models.data?.length
          ? "Models LLM nodes can select. The default is used when a node does not pick one."
          : "Models LLM nodes can select. No default is set, so every LLM node must pick a model."
      }
      actions={models.data?.length ? add : undefined}
    >
      {models.isPending ? (
        <LoadingState rows={5} />
      ) : models.error ? (
        <ErrorState error={models.error} onRetry={() => void models.refetch()} />
      ) : models.data.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title="No models registered"
          body={noProviders ? "Add a provider above, then register the models it offers." : "Register a model by its API name, context window and price."}
          action={add}
        />
      ) : (
        <DataTable
          rows={models.data}
          getRowId={(m) => m.id}
          searchText={(m) => `${m.display_name} ${m.model_name} ${m.provider_name}`}
          searchPlaceholder="Filter models"
          initialSort={{ id: "name", desc: false }}
          rowClassName={(m) => cn(!m.is_active && "[&>td:not(:last-child)]:text-fg-muted")}
          columns={[
            {
              id: "name",
              header: "Model",
              sortValue: (m) => m.display_name.toLowerCase(),
              cell: (m) => (
                <div className="flex min-w-0 flex-col">
                  <span className="flex items-center gap-1.5 font-medium">
                    {m.display_name}
                    {m.is_default ? (
                      <Badge tone="info" aria-label="Default model">
                        Default
                      </Badge>
                    ) : null}
                  </span>
                  <span className="font-mono text-xs text-fg-muted">{m.model_name}</span>
                </div>
              ),
            },
            { id: "provider", header: "Provider", sortValue: (m) => m.provider_name.toLowerCase(), cell: (m) => <span className="text-fg-muted">{m.provider_name}</span> },
            {
              id: "ctx",
              header: "Context",
              align: "right",
              sortValue: (m) => m.context_window,
              cell: (m) => <span title={`${m.context_window.toLocaleString("en")} tokens`}>{compact(m.context_window)}</span>,
            },
            {
              id: "caps",
              header: "Supports",
              cell: (m) =>
                m.supports_tools || m.supports_json_schema ? (
                  <span className="flex gap-1">
                    <Capability on={m.supports_tools} label="Tools" />
                    <Capability on={m.supports_json_schema} label="JSON schema" />
                  </span>
                ) : (
                  <span className="text-xs text-fg-subtle">Text only</span>
                ),
            },
            {
              id: "price",
              header: "In / out per MTok",
              align: "right",
              sortValue: (m) => Number(m.input_price_per_mtok),
              cell: (m) =>
                Number(m.input_price_per_mtok) === 0 && Number(m.output_price_per_mtok) === 0 ? (
                  <span className="text-fg-muted">Free</span>
                ) : (
                  <span className="whitespace-nowrap">
                    {pricePerMTok(m.input_price_per_mtok)} <span className="text-fg-subtle">/</span> {pricePerMTok(m.output_price_per_mtok)}
                  </span>
                ),
            },
            {
              id: "active",
              header: "Active",
              cell: (m) => (
                <Gate allowed={isOwner} reason={OWNER_ONLY}>
                  <Switch checked={m.is_active} onCheckedChange={(is_active) => setActive.mutate({ id: m.id, is_active })} aria-label={`${m.display_name} active`} />
                </Gate>
              ),
            },
            {
              id: "actions",
              header: <span className="sr-only">Actions</span>,
              align: "right",
              cell: (m) => (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button size="icon" variant="ghost" aria-label={`Actions for ${m.display_name}`}>
                      <MoreHorizontal />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent>
                    <DropdownMenuItem disabled={!isOwner} onSelect={() => openEditor(m)}>
                      <Pencil /> Edit model
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      disabled={!isOwner || m.is_default || !m.is_active}
                      onSelect={() => setDefault.mutate(m.id, { onSuccess: () => toast.success(`${m.display_name} is now the default model`) })}
                    >
                      <Star /> {m.is_default ? "Default model" : "Make default"}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem tone="danger" disabled={!isOwner} onSelect={() => setDeleting(m)}>
                      <Trash2 /> Delete model
                    </DropdownMenuItem>
                    {!isOwner ? <p className="px-2 py-1 text-2xs text-fg-subtle">{OWNER_ONLY}</p> : null}
                  </DropdownMenuContent>
                </DropdownMenu>
              ),
            },
          ]}
        />
      )}

      <ModelDrawer open={drawerOpen} onOpenChange={setDrawerOpen} model={editing} providers={providerList} />

      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={`Delete ${deleting?.display_name ?? "model"}?`}
        body={
          <>
            <span className="font-mono text-fg">{deleting?.model_name}</span> will no longer be selectable. Pipeline nodes that reference it will
            need a different model.{deleting?.is_default ? " It is the current default, so the workspace will have no default model." : ""}
          </>
        }
        confirmLabel="Delete model"
        tone="danger"
        loading={del.isPending}
        onConfirm={() =>
          deleting &&
          del.mutate(deleting.id, {
            onSuccess: () => {
              toast.success(`Deleted ${deleting.display_name}`);
              setDeleting(null);
            },
          })
        }
      />
    </Section>
  );
}
