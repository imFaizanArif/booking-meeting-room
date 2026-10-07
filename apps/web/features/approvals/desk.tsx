"use client";

import { Inbox } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { EmptyState } from "@/components/ui/states";
import { cn } from "@/lib/utils";

import { ApprovalDetail } from "./approval-detail";
import { ApprovalList } from "./approval-list";
import { useApprovals } from "./queries";

const FILTERS = [
  { id: "pending", label: "Pending" },
  { id: "approved", label: "Approved" },
  { id: "rejected", label: "Rejected" },
  { id: "all", label: "All" },
] as const;
type Filter = (typeof FILTERS)[number]["id"];

/** Two-pane action desk: queue on the left, the selected approval on the right. */
export function ApprovalDesk({ selectedId }: { selectedId?: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const filter = (FILTERS.find((f) => f.id === params.get("filter"))?.id ?? "pending") as Filter;
  const list = useApprovals(filter);

  // j/k move through the queue, like a mail client.
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      if (!list.data?.items.length || target?.closest("input, textarea, [contenteditable=true], .cm-editor")) return;
      if (e.key !== "j" && e.key !== "k") return;
      const items = list.data.items;
      const index = items.findIndex((a) => a.id === selectedId);
      const next = e.key === "j" ? Math.min(items.length - 1, index + 1) : Math.max(0, index - 1);
      const item = items[next < 0 ? 0 : next];
      if (item) router.push(`/approvals/${item.id}${filter !== "pending" ? `?filter=${filter}` : ""}`);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [list.data, selectedId, router, filter]);

  return (
    <div className="flex h-full min-h-0">
      <section className="flex w-[340px] shrink-0 flex-col border-r border-border bg-surface" aria-label="Approval queue">
        <header className="border-b border-border px-4 pb-0 pt-4">
          <div className="flex items-baseline justify-between">
            <h1 className="text-base font-semibold">Approvals</h1>
            {list.data ? <span className="tabular text-xs text-fg-subtle">{list.data.total}</span> : null}
          </div>
          <nav className="mt-2 flex gap-4" aria-label="Filter approvals">
            {FILTERS.map((f) => (
              <Link
                key={f.id}
                href={f.id === "pending" ? "/approvals" : `/approvals?filter=${f.id}`}
                aria-current={filter === f.id ? "page" : undefined}
                className={cn(
                  "-mb-px border-b-2 border-transparent pb-2 text-xs text-fg-muted hover:text-fg",
                  filter === f.id && "border-fg font-medium text-fg",
                )}
              >
                {f.label}
              </Link>
            ))}
          </nav>
        </header>
        <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
          <ApprovalList
            items={list.data?.items}
            selectedId={selectedId}
            isPending={list.isPending}
            error={list.error}
            onRetry={() => void list.refetch()}
            filter={filter}
          />
        </div>
        <p className="border-t border-border px-4 py-2 text-2xs text-fg-subtle">
          <kbd className="font-mono">j</kbd>/<kbd className="font-mono">k</kbd> to move through the queue
        </p>
      </section>
      <section className="min-w-0 flex-1 bg-bg" aria-label="Approval detail">
        {selectedId ? (
          <ApprovalDetail id={selectedId} />
        ) : (
          <div className="p-8">
            <EmptyState
              icon={Inbox}
              title="Select an approval"
              body="Each item is a paused execution. Approve to run the action exactly as shown, edit the arguments first, ask the agent for a new proposal, or reject with a reason."
            />
          </div>
        )}
      </section>
    </div>
  );
}
