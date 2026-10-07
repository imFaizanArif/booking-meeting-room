"use client";

import { CalendarClock, History, MoreHorizontal, Pencil, Plus, Trash2 } from "lucide-react";
import * as React from "react";

import { PageContainer } from "@/components/shell/page-container";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger, Tooltip } from "@/components/ui/menus";
import { ConfirmDialog } from "@/components/ui/overlay";
import { PageHeader } from "@/components/ui/page";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { Switch } from "@/components/ui/toggles";
import { Gate } from "@/components/ui-extra/gate";
import { canOperate, useMe } from "@/features/auth/queries";
import type { Schemas } from "@/lib/api/client";
import { dateTime, relativeTime } from "@/lib/format";

import { describeSchedule, scheduleSummary } from "./describe";
import { FiresDrawer } from "./fires-drawer";
import { useDeleteSchedule, useSetScheduleActive } from "./mutations";
import { useSchedules } from "./queries";
import { ScheduleDrawer } from "./schedule-drawer";

type ScheduleOut = Schemas["ScheduleOut"];

function When({ schedule }: { schedule: ScheduleOut }) {
  const d = describeSchedule(schedule);
  return (
    <div className="flex min-w-0 flex-col">
      {d.text ? <span>{d.text}</span> : <span className="font-mono text-xs">{d.cron}</span>}
      <span className="text-2xs text-fg-subtle">
        {d.text && d.cron ? <span className="font-mono">{d.cron}</span> : null}
        {d.text && d.cron && d.timezone ? " · " : null}
        {d.timezone ?? (schedule.kind === "interval" ? "Interval" : null)}
      </span>
    </div>
  );
}

function TimeCell({ value, muted }: { value: string | null; muted?: boolean }) {
  if (!value) return <span className="text-fg-subtle">—</span>;
  return (
    <div className="flex flex-col">
      <span className={muted ? "text-fg-muted tabular" : "tabular"}>{dateTime(value)}</span>
      <span className="text-2xs text-fg-subtle">{relativeTime(value)}</span>
    </div>
  );
}

export function SchedulesPage() {
  const me = useMe();
  const canEdit = canOperate(me.data?.role);
  const schedules = useSchedules();
  const setActive = useSetScheduleActive();
  const remove = useDeleteSchedule();

  const [editing, setEditing] = React.useState<ScheduleOut | null>(null);
  const [drawerOpen, setDrawerOpen] = React.useState(false);
  const [firesFor, setFiresFor] = React.useState<ScheduleOut | null>(null);
  const [deleting, setDeleting] = React.useState<ScheduleOut | null>(null);

  function openCreate() {
    setEditing(null);
    setDrawerOpen(true);
  }
  function openEdit(s: ScheduleOut) {
    setEditing(s);
    setDrawerOpen(true);
  }

  const reason = "Operators and owners can change schedules.";
  const newButton = (
    <Gate allowed={canEdit} reason={reason}>
      <Button variant="primary" onClick={openCreate}>
        <Plus /> New schedule
      </Button>
    </Gate>
  );

  return (
    <PageContainer>
      <PageHeader
        title="Schedules"
        description="Start pipelines on a timer. The scheduler claims each fire once, even with several instances running."
        actions={schedules.data?.length ? newButton : null}
      />
      {schedules.isPending ? (
        <LoadingState rows={5} />
      ) : schedules.error ? (
        <ErrorState error={schedules.error} onRetry={() => void schedules.refetch()} />
      ) : schedules.data.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          title="No schedules yet"
          body="A schedule runs a pipeline with a fixed input every few minutes, once a day, or on a cron expression."
          action={newButton}
        />
      ) : (
        <DataTable
          rows={schedules.data}
          getRowId={(s) => s.id}
          searchText={(s) => `${s.name} ${s.pipeline_name} ${scheduleSummary(s)}`}
          searchPlaceholder="Filter schedules"
          initialSort={{ id: "next", desc: false }}
          rowClassName={(s) => (s.is_active ? undefined : "[&>td]:text-fg-muted")}
          columns={[
            { id: "name", header: "Name", sortValue: (s) => s.name.toLowerCase(), cell: (s) => <span className="font-medium text-fg">{s.name}</span> },
            { id: "pipeline", header: "Pipeline", sortValue: (s) => s.pipeline_name.toLowerCase(), cell: (s) => <span className="text-fg-muted">{s.pipeline_name || "—"}</span> },
            { id: "when", header: "When", cell: (s) => <When schedule={s} /> },
            {
              id: "next",
              header: "Next run",
              sortValue: (s) => (s.is_active && s.next_run_at ? s.next_run_at : "9999"),
              cell: (s) => (s.is_active ? <TimeCell value={s.next_run_at} /> : <span className="text-fg-subtle">Paused</span>),
            },
            { id: "last", header: "Last run", sortValue: (s) => s.last_run_at ?? "", cell: (s) => <TimeCell value={s.last_run_at} muted /> },
            {
              id: "overlap",
              header: "Overlap",
              cell: (s) => (
                <Tooltip content={s.overlap_policy === "skip" ? "Skips a fire while the previous run is still going" : "Starts a new run even if the previous one is still going"}>
                  <span>
                    <Badge tone="outline">{s.overlap_policy === "skip" ? "Skip" : "Queue"}</Badge>
                  </span>
                </Tooltip>
              ),
            },
            {
              id: "active",
              header: "Active",
              cell: (s) => (
                <Switch
                  aria-label={`${s.is_active ? "Pause" : "Activate"} ${s.name}`}
                  checked={s.is_active}
                  disabled={!canEdit || (setActive.isPending && setActive.variables?.schedule.id === s.id)}
                  onCheckedChange={(active) => setActive.mutate({ schedule: s, active })}
                />
              ),
            },
            {
              id: "actions",
              header: <span className="sr-only">Actions</span>,
              align: "right",
              cell: (s) => (
                <div className="flex items-center justify-end gap-1">
                  <Button size="sm" variant="ghost" onClick={() => setFiresFor(s)}>
                    <History /> View fires
                  </Button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button size="icon" variant="ghost" aria-label={`More actions for ${s.name}`}>
                        <MoreHorizontal />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent>
                      <DropdownMenuItem disabled={!canEdit} onSelect={() => openEdit(s)}>
                        <Pencil /> Edit schedule
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem tone="danger" disabled={!canEdit} onSelect={() => setDeleting(s)}>
                        <Trash2 /> Delete schedule
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              ),
            },
          ]}
        />
      )}
      {!canEdit && me.data ? <p className="text-xs text-fg-subtle">You have read-only access. {reason}</p> : null}

      <ScheduleDrawer open={drawerOpen} onOpenChange={setDrawerOpen} schedule={editing} />
      <FiresDrawer schedule={firesFor} onOpenChange={(o) => !o && setFiresFor(null)} />
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title="Delete schedule"
        tone="danger"
        confirmLabel="Delete schedule"
        loading={remove.isPending}
        body={
          <>
            <span className="font-medium text-fg">{deleting?.name}</span> will stop firing and its fire history is removed. Executions it already started are kept.
          </>
        }
        onConfirm={() => deleting && remove.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
      />
    </PageContainer>
  );
}
