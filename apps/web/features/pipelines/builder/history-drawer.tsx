"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { DiffViewer } from "@/components/ui/diff-viewer";
import { Drawer } from "@/components/ui/overlay";
import { LoadingState } from "@/components/ui/states";
import type { Schemas } from "@/lib/api/client";
import { dateTime, relativeTime } from "@/lib/format";
import { cn } from "@/lib/utils";

import { type Graph, toGraph } from "../graph";
import { usePipelineVersion } from "../queries";

/** Version history: pick two versions to diff, restore an old graph into the editor. */
export function HistoryDrawer({ open, onOpenChange, pipelineId, versions, latest, onRestore }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pipelineId: string;
  versions: Schemas["PipelineVersionSummary"][];
  latest: number;
  onRestore: (graph: Graph, version: number) => void;
}) {
  const [left, setLeft] = React.useState<number | null>(null);
  const [right, setRight] = React.useState<number | null>(latest);
  const [wasOpen, setWasOpen] = React.useState(open);
  if (wasOpen !== open) {
    setWasOpen(open);
    if (open) {
      setRight(latest);
      setLeft(versions.find((v) => v.version < latest)?.version ?? null);
    }
  }
  const a = usePipelineVersion(pipelineId, left);
  const b = usePipelineVersion(pipelineId, right);

  function pick(version: number) {
    if (version === right) return;
    if (left === version) setLeft(null);
    else setLeft(version);
  }

  return (
    <Drawer
      open={open}
      onOpenChange={onOpenChange}
      title="Version history"
      description="Saved versions are immutable. Select one to compare it with the selected newer version."
      className="max-w-3xl"
      footer={
        left != null && a.data ? (
          <Button variant="primary" onClick={() => { onRestore(toGraph(a.data.graph), left); onOpenChange(false); }}>
            Load v{left} into the editor
          </Button>
        ) : undefined
      }
    >
      <div className="flex flex-col gap-4">
        <ul className="flex flex-col divide-y divide-border rounded-md border border-border">
          {versions.map((v) => (
            <li key={v.id} className={cn("flex items-center gap-3 px-3 py-2", (v.version === left || v.version === right) && "bg-subtle")}>
              <span className="w-10 font-mono text-xs font-medium">v{v.version}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm">{v.change_note || "No change note"}</span>
                <span className="text-2xs text-fg-subtle" title={dateTime(v.created_at)}>
                  {relativeTime(v.created_at)} · {v.graph_hash.slice(0, 10)}
                </span>
              </span>
              <Button size="sm" variant={v.version === right ? "secondary" : "ghost"} onClick={() => { setRight(v.version); if (left != null && left >= v.version) setLeft(null); }}>
                {v.version === right ? "Newer" : "Set newer"}
              </Button>
              <Button size="sm" variant={v.version === left ? "secondary" : "ghost"} disabled={right != null && v.version >= right} onClick={() => pick(v.version)}>
                {v.version === left ? "Older" : "Compare"}
              </Button>
            </li>
          ))}
        </ul>
        {left != null && right != null ? (
          a.isPending || b.isPending ? (
            <LoadingState rows={6} />
          ) : (
            <div className="flex flex-col gap-1">
              <p className="text-xs text-fg-muted">
                Changes from v{left} to v{right}
              </p>
              <DiffViewer before={a.data?.graph} after={b.data?.graph} className="max-h-[50vh]" />
            </div>
          )
        ) : (
          <p className="text-sm text-fg-muted">Choose an older version to see what changed.</p>
        )}
      </div>
    </Drawer>
  );
}
