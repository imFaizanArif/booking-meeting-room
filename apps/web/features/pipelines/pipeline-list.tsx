"use client";

import { Archive, ArchiveRestore, MoreHorizontal, Plus, SquarePen, Trash2, Workflow } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { PageContainer } from "@/components/shell/page-container";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/menus";
import { ConfirmDialog } from "@/components/ui/overlay";
import { PageHeader } from "@/components/ui/page";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { StatusIndicator } from "@/components/ui/status";
import { Checkbox } from "@/components/ui/toggles";
import { canOperate, useMe } from "@/features/auth/queries";
import type { Schemas } from "@/lib/api/client";
import { relativeTime } from "@/lib/format";

import { useArchivePipeline, useDeletePipeline } from "./mutations";
import { NewPipelineModal } from "./new-pipeline-modal";
import { usePipelines } from "./queries";

type Pipeline = Schemas["PipelineOut"];

export function PipelineList() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const me = useMe();
  const operator = canOperate(me.data?.role);
  const owner = me.data?.role === "owner";
  const [showArchived, setShowArchived] = React.useState(false);
  const { data, isPending, error, refetch } = usePipelines(showArchived);
  const archive = useArchivePipeline();
  const remove = useDeletePipeline();
  const [confirm, setConfirm] = React.useState<{ kind: "archive" | "delete"; pipeline: Pipeline } | null>(null);

  const newOpen = params.get("new") === "1";
  const setNewOpen = (open: boolean) => {
    const next = new URLSearchParams(params.toString());
    if (open) next.set("new", "1");
    else next.delete("new");
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  function runConfirm() {
    if (!confirm) return;
    const done = { onSuccess: () => setConfirm(null) };
    if (confirm.kind === "archive") archive.mutate({ id: confirm.pipeline.id, archived: true }, done);
    else remove.mutate(confirm.pipeline.id, done);
  }

  return (
    <PageContainer>
      <PageHeader
        title="Pipelines"
        description="Versioned graphs of model, agent, tool and approval steps. Every saved version is immutable and can be run, scheduled or restored."
        actions={
          operator ? (
            <Button variant="primary" onClick={() => setNewOpen(true)}>
              <Plus /> New pipeline
            </Button>
          ) : null
        }
      />
      {isPending ? (
        <LoadingState rows={6} />
      ) : error ? (
        <ErrorState error={error} onRetry={() => void refetch()} />
      ) : data.length === 0 && !showArchived ? (
        <EmptyState
          icon={Workflow}
          title="No pipelines yet"
          body="A pipeline connects a trigger to models, MCP tools, conditions and human approvals. Create one to open the builder."
          action={
            operator ? (
              <Button variant="primary" size="sm" onClick={() => setNewOpen(true)}>
                <Plus /> New pipeline
              </Button>
            ) : null
          }
        />
      ) : (
        <DataTable
          rows={data}
          getRowId={(p) => p.id}
          onRowClick={(p) => router.push(`/pipelines/${p.id}`)}
          searchText={(p) => `${p.name} ${p.description ?? ""} ${p.slug}`}
          searchPlaceholder="Filter pipelines"
          initialSort={{ id: "updated", desc: true }}
          toolbar={
            <label className="ml-auto flex items-center gap-2 text-xs text-fg-muted">
              <Checkbox checked={showArchived} onCheckedChange={(c) => setShowArchived(c === true)} aria-label="Show archived pipelines" />
              Show archived
            </label>
          }
          empty={showArchived ? "No pipelines, archived or active." : undefined}
          columns={[
            {
              id: "name",
              header: "Name",
              sortValue: (p) => p.name.toLowerCase(),
              cell: (p) => (
                <div className="min-w-0 max-w-[420px]">
                  <div className="flex items-center gap-2">
                    <Link href={`/pipelines/${p.id}`} onClick={(e) => e.stopPropagation()} className="truncate font-medium hover:underline">
                      {p.name}
                    </Link>
                    {p.is_archived ? <Badge>Archived</Badge> : null}
                  </div>
                  {p.description ? <p className="truncate text-xs text-fg-muted">{p.description}</p> : null}
                </div>
              ),
            },
            {
              id: "version",
              header: "Version",
              sortValue: (p) => p.latest_version_number,
              cell: (p) => <span className="font-mono text-xs text-fg-muted">v{p.latest_version_number}</span>,
            },
            { id: "nodes", header: "Nodes", align: "right", sortValue: (p) => p.node_count, cell: (p) => p.node_count },
            {
              id: "last",
              header: "Last execution",
              sortValue: (p) => p.last_execution_at ?? "",
              cell: (p) =>
                p.last_execution_status ? (
                  <span className="flex items-center gap-2">
                    <StatusIndicator kind="execution" value={p.last_execution_status} />
                    <span className="text-xs text-fg-subtle">{relativeTime(p.last_execution_at)}</span>
                  </span>
                ) : (
                  <span className="text-xs text-fg-subtle">Never run</span>
                ),
            },
            { id: "schedules", header: "Schedules", align: "right", sortValue: (p) => p.schedule_count, cell: (p) => (p.schedule_count ? p.schedule_count : <span className="text-fg-subtle">—</span>) },
            {
              id: "updated",
              header: "Updated",
              align: "right",
              sortValue: (p) => p.updated_at,
              cell: (p) => <span className="text-xs text-fg-muted">{relativeTime(p.updated_at)}</span>,
            },
            {
              id: "actions",
              header: <span className="sr-only">Actions</span>,
              className: "w-10",
              cell: (p) => (
                <div onClick={(e) => e.stopPropagation()}>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" aria-label={`Actions for ${p.name}`}>
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent>
                      <DropdownMenuItem onSelect={() => router.push(`/pipelines/${p.id}`)}>
                        <SquarePen /> Open builder
                      </DropdownMenuItem>
                      {operator ? (
                        p.is_archived ? (
                          <DropdownMenuItem onSelect={() => archive.mutate({ id: p.id, archived: false })}>
                            <ArchiveRestore /> Unarchive
                          </DropdownMenuItem>
                        ) : (
                          <DropdownMenuItem onSelect={() => setConfirm({ kind: "archive", pipeline: p })}>
                            <Archive /> Archive
                          </DropdownMenuItem>
                        )
                      ) : null}
                      {owner ? (
                        <>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem tone="danger" onSelect={() => setConfirm({ kind: "delete", pipeline: p })}>
                            <Trash2 /> Delete
                          </DropdownMenuItem>
                        </>
                      ) : null}
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ),
            },
          ]}
        />
      )}

      <NewPipelineModal open={newOpen} onOpenChange={setNewOpen} />
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm?.kind === "delete" ? `Delete ${confirm.pipeline.name}?` : `Archive ${confirm?.pipeline.name ?? ""}?`}
        body={
          confirm?.kind === "delete" ? (
            <>
              A pipeline that has never run is deleted with all its versions. If it has executions it is archived instead, so
              their history stays reproducible.
            </>
          ) : (
            <>Archived pipelines are hidden from the list and cannot be run. Schedules stay attached; you can unarchive at any time.</>
          )
        }
        confirmLabel={confirm?.kind === "delete" ? "Delete pipeline" : "Archive pipeline"}
        tone={confirm?.kind === "delete" ? "danger" : "default"}
        loading={archive.isPending || remove.isPending}
        onConfirm={runConfirm}
      />
    </PageContainer>
  );
}
