"use client";

import Link from "next/link";

import { Badge, type Tone } from "@/components/ui/badge";
import { DataTable } from "@/components/ui/data-table";
import { Drawer } from "@/components/ui/overlay";
import { ErrorState, LoadingState } from "@/components/ui/states";
import type { Schemas } from "@/lib/api/client";
import { dateTime, relativeTime, shortId } from "@/lib/format";

import { scheduleSummary } from "./describe";
import { useScheduleFires } from "./queries";

const OUTCOME: Record<string, { tone: Tone; label: string }> = {
  enqueued: { tone: "ok", label: "Enqueued" },
  skipped_overlap: { tone: "warn", label: "Skipped, overlap" },
  failed: { tone: "danger", label: "Failed" },
  claimed: { tone: "neutral", label: "Claimed" },
};

export function OutcomeBadge({ outcome }: { outcome: string }) {
  const spec = OUTCOME[outcome] ?? { tone: "neutral" as Tone, label: outcome };
  return <Badge tone={spec.tone}>{spec.label}</Badge>;
}

export function FiresDrawer({ schedule, onOpenChange }: { schedule: Schemas["ScheduleOut"] | null; onOpenChange: (open: boolean) => void }) {
  const fires = useScheduleFires(schedule?.id);
  return (
    <Drawer
      open={!!schedule}
      onOpenChange={onOpenChange}
      title={schedule ? `Fires · ${schedule.name}` : "Fires"}
      description={schedule ? `${schedule.pipeline_name} · ${scheduleSummary(schedule)}. Most recent 50.` : undefined}
      className="max-w-2xl"
    >
      {fires.isPending ? (
        <LoadingState rows={6} />
      ) : fires.error ? (
        <ErrorState error={fires.error} onRetry={() => void fires.refetch()} />
      ) : (
        <DataTable
          rows={fires.data}
          getRowId={(f) => f.id}
          empty="This schedule has not fired yet. Fires appear here once the scheduler claims a run."
          columns={[
            {
              id: "fire_at",
              header: "Fire time",
              cell: (f) => (
                <div className="flex flex-col">
                  <span className="tabular">{dateTime(f.fire_at)}</span>
                  <span className="text-2xs text-fg-subtle">{relativeTime(f.fire_at)}</span>
                </div>
              ),
            },
            { id: "outcome", header: "Outcome", cell: (f) => <OutcomeBadge outcome={f.outcome} /> },
            {
              id: "execution",
              header: "Execution",
              cell: (f) =>
                f.execution_id ? (
                  <Link href={`/executions/${f.execution_id}`} className="font-mono text-xs hover:underline">
                    {shortId(f.execution_id)}
                  </Link>
                ) : (
                  <span className="text-fg-subtle">—</span>
                ),
            },
            { id: "fired_by", header: "Fired by", cell: (f) => <span className="font-mono text-xs text-fg-muted">{f.fired_by}</span> },
          ]}
        />
      )}
    </Drawer>
  );
}
