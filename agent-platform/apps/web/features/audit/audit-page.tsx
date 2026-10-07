"use client";

import { ArrowUpRight, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";

import { PageContainer } from "@/components/shell/page-container";
import { Button } from "@/components/ui/button";
import { DataTable } from "@/components/ui/data-table";
import { Input } from "@/components/ui/input";
import { JsonViewer } from "@/components/ui/json-viewer";
import { Drawer } from "@/components/ui/overlay";
import { DescriptionList, PageHeader, Section } from "@/components/ui/page";
import { Select } from "@/components/ui/select";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { CopyText } from "@/components/ui-extra/copy-text";
import type { Schemas } from "@/lib/api/client";
import { dateTime, humanize, relativeTime, shortId } from "@/lib/format";
import { cn } from "@/lib/utils";

import { AUDIT_ENTITY_TYPES, AUDIT_EVENT_TYPES, AUDIT_PAGE_SIZE, type AuditFilters, useAuditLog } from "./queries";

type AuditOut = Schemas["AuditOut"];

const ALL = "__all__";
const FILTER_KEYS = ["q", "event_type", "entity_type", "actor", "since", "until"] as const;
type FilterKey = (typeof FILTER_KEYS)[number];

function useUrlFilters() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const filters: AuditFilters = {
    q: params.get("q") ?? undefined,
    event_type: params.get("event_type") ?? undefined,
    entity_type: params.get("entity_type") ?? undefined,
    actor: params.get("actor") ?? undefined,
    since: params.get("since") ?? undefined,
    until: params.get("until") ?? undefined,
    offset: Math.max(0, Number(params.get("offset") ?? 0) || 0),
  };

  const update = React.useCallback(
    (patch: Partial<Record<FilterKey | "offset", string | number | undefined>>) => {
      const next = new URLSearchParams(params.toString());
      for (const [key, value] of Object.entries(patch)) {
        if (value === undefined || value === "" || value === 0) next.delete(key);
        else next.set(key, String(value));
      }
      // Any filter change goes back to the first page.
      if (!("offset" in patch)) next.delete("offset");
      const qs = next.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [params, router, pathname],
  );

  return { filters, update };
}

/** Text input that commits after a pause and follows the URL when it changes from elsewhere (back/forward). */
function DebouncedInput({ value, onCommit, ...props }: { value: string; onCommit: (value: string) => void } & Omit<React.InputHTMLAttributes<HTMLInputElement>, "value" | "onChange">) {
  const [text, setText] = React.useState(value);
  const [seen, setSeen] = React.useState(value);
  const [committed, setCommitted] = React.useState(value);
  if (value !== seen) {
    setSeen(value);
    if (value !== committed) {
      setText(value);
      setCommitted(value);
    }
  }
  React.useEffect(() => {
    if (text === committed) return;
    const t = setTimeout(() => {
      setCommitted(text);
      onCommit(text);
    }, 300);
    return () => clearTimeout(t);
  }, [text, committed, onCommit]);
  return <Input value={text} onChange={(e) => setText(e.target.value)} {...props} />;
}

function FilterLabel({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="text-2xs font-medium text-fg-muted">
      {children}
    </label>
  );
}

function entityLabel(row: AuditOut): React.ReactNode {
  if (!row.entity_type) return <span className="text-fg-subtle">—</span>;
  const id = row.entity_id ? (row.entity_id.length > 12 ? shortId(row.entity_id) : row.entity_id) : null;
  return (
    <span className="inline-flex items-baseline gap-1.5">
      <span>{humanize(row.entity_type)}</span>
      {id ? <span className="font-mono text-xs text-fg-muted">{id}</span> : null}
    </span>
  );
}

function AuditDetail({ row, onOpenChange }: { row: AuditOut | null; onOpenChange: (open: boolean) => void }) {
  return (
    <Drawer open={!!row} onOpenChange={onOpenChange} title={row ? <span className="font-mono">{row.event_type}</span> : "Event"} description={row ? dateTime(row.created_at) : undefined}>
      {row ? (
        <div className="flex flex-col gap-6">
          <DescriptionList
            items={[
              { label: "Time", value: <span className="tabular">{`${dateTime(row.created_at)} (${relativeTime(row.created_at)})`}</span> },
              {
                label: "Actor",
                value: (
                  <span>
                    {row.actor_label ?? "—"} <span className="text-fg-muted">· {row.actor_type}</span>
                  </span>
                ),
              },
              { label: "Event", value: <span className="font-mono text-xs">{row.event_type}</span> },
              {
                label: "Entity",
                value: row.entity_type ? (
                  <span>
                    {humanize(row.entity_type)} {row.entity_id ? <CopyText value={row.entity_id} label="Entity id" /> : null}
                  </span>
                ) : (
                  "—"
                ),
              },
              {
                label: "Execution",
                value: row.execution_id ? (
                  <Link href={`/executions/${row.execution_id}`} className="inline-flex items-center gap-1 font-mono text-xs hover:underline">
                    {row.execution_id} <ArrowUpRight className="size-3" aria-hidden />
                  </Link>
                ) : (
                  "—"
                ),
              },
              { label: "Request", value: row.request_id ? <CopyText value={row.request_id} label="Request id" /> : "—" },
              { label: "IP", value: row.ip ? <span className="font-mono text-xs">{row.ip}</span> : "—" },
            ]}
          />
          <Section title="Payload" description="Secrets and credentials are redacted before the event is stored.">
            {Object.keys(row.payload ?? {}).length ? <JsonViewer value={row.payload} defaultOpen={3} /> : <p className="text-sm text-fg-muted">No payload recorded.</p>}
          </Section>
        </div>
      ) : null}
    </Drawer>
  );
}

function AuditLog() {
  const { filters, update } = useUrlFilters();
  const log = useAuditLog(filters);
  const [selected, setSelected] = React.useState<AuditOut | null>(null);
  const active = FILTER_KEYS.some((k) => !!filters[k]);
  const commitQ = React.useCallback((v: string) => update({ q: v.trim() }), [update]);
  const commitActor = React.useCallback((v: string) => update({ actor: v.trim() }), [update]);

  return (
    <>
      <div className="flex flex-wrap items-end gap-3" role="search" aria-label="Filter audit events">
        <div className="flex flex-col gap-1">
          <FilterLabel htmlFor="a-q">Search</FilterLabel>
          <div className="relative w-60">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" aria-hidden />
            <DebouncedInput id="a-q" value={filters.q ?? ""} onCommit={commitQ} placeholder="Event, entity id or actor" className="h-7 pl-8 text-xs" />
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <FilterLabel htmlFor="a-event">Event type</FilterLabel>
          <Select
            id="a-event"
            size="sm"
            className="w-48 font-mono"
            value={filters.event_type ?? ALL}
            onValueChange={(v) => update({ event_type: v === ALL ? undefined : v })}
            options={[{ value: ALL, label: "All events" }, ...AUDIT_EVENT_TYPES.map((e) => ({ value: e, label: e }))]}
          />
        </div>
        <div className="flex flex-col gap-1">
          <FilterLabel htmlFor="a-entity">Entity type</FilterLabel>
          <Select
            id="a-entity"
            size="sm"
            className="w-44"
            value={filters.entity_type ?? ALL}
            onValueChange={(v) => update({ entity_type: v === ALL ? undefined : v })}
            options={[{ value: ALL, label: "All entities" }, ...AUDIT_ENTITY_TYPES.map((e) => ({ value: e, label: humanize(e) }))]}
          />
        </div>
        <div className="flex flex-col gap-1">
          <FilterLabel htmlFor="a-actor">Actor</FilterLabel>
          <DebouncedInput id="a-actor" value={filters.actor ?? ""} onCommit={commitActor} placeholder="Email or worker" className="h-7 w-44 text-xs" />
        </div>
        <div className="flex flex-col gap-1">
          <FilterLabel htmlFor="a-since">Since</FilterLabel>
          <Input id="a-since" type="datetime-local" className="h-7 w-48 text-xs tabular" value={filters.since ?? ""} max={filters.until} onChange={(e) => update({ since: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1">
          <FilterLabel htmlFor="a-until">Until</FilterLabel>
          <Input id="a-until" type="datetime-local" className="h-7 w-48 text-xs tabular" value={filters.until ?? ""} min={filters.since} onChange={(e) => update({ until: e.target.value })} />
        </div>
        {active ? (
          <Button size="sm" variant="ghost" onClick={() => update({ q: undefined, event_type: undefined, entity_type: undefined, actor: undefined, since: undefined, until: undefined })}>
            <X /> Clear filters
          </Button>
        ) : null}
      </div>

      {log.isPending ? (
        <LoadingState rows={10} />
      ) : log.error ? (
        <ErrorState error={log.error} onRetry={() => void log.refetch()} />
      ) : (
        <div className={cn("flex flex-col gap-2 transition-opacity duration-100", log.isPlaceholderData && "opacity-60")} aria-busy={log.isFetching}>
          <p className="text-xs text-fg-muted tabular" aria-live="polite">
            {log.data.total === 0 ? "No events" : `${log.data.total.toLocaleString()} event${log.data.total === 1 ? "" : "s"}`}
            {active ? " match these filters" : ""}
          </p>
          <DataTable
            rows={log.data.items}
            getRowId={(r) => r.id}
            onRowClick={setSelected}
            server={{ total: log.data.total, limit: AUDIT_PAGE_SIZE, offset: log.data.offset, onOffsetChange: (offset) => update({ offset }) }}
            empty={active ? "No events match these filters. Widen the time range or clear a filter." : "No audit events yet. Sign-ins, configuration changes, secret access and tool calls are recorded here."}
            columns={[
              {
                id: "time",
                header: "Time",
                className: "whitespace-nowrap",
                cell: (r) => (
                  <span className="font-mono text-xs tabular" title={relativeTime(r.created_at)}>
                    {dateTime(r.created_at)}
                  </span>
                ),
              },
              {
                id: "actor",
                header: "Actor",
                cell: (r) => (
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate">{r.actor_label ?? "—"}</span>
                    <span className="text-2xs text-fg-subtle">{r.actor_type}</span>
                  </div>
                ),
              },
              { id: "event", header: "Event", cell: (r) => <span className={cn("font-mono text-xs", /failed|denied/.test(r.event_type) && "text-danger")}>{r.event_type}</span> },
              {
                id: "entity",
                header: "Entity",
                cell: (r) =>
                  r.execution_id ? (
                    <div className="flex flex-col">
                      {entityLabel(r)}
                      <Link href={`/executions/${r.execution_id}`} onClick={(e) => e.stopPropagation()} className="inline-flex items-center gap-0.5 text-2xs text-fg-muted hover:text-fg hover:underline">
                        Execution <span className="font-mono">{shortId(r.execution_id)}</span>
                        <ArrowUpRight className="size-3" aria-hidden />
                      </Link>
                    </div>
                  ) : (
                    entityLabel(r)
                  ),
              },
              {
                id: "request",
                header: "Request id",
                cell: (r) => (r.request_id ? <CopyText value={r.request_id} display={r.request_id.slice(0, 12)} label="Request id" /> : <span className="text-fg-subtle">—</span>),
              },
            ]}
          />
        </div>
      )}
      <AuditDetail row={selected} onOpenChange={(o) => !o && setSelected(null)} />
    </>
  );
}

export function AuditPage() {
  return (
    <PageContainer>
      <PageHeader title="Audit log" description="Append-only record of who did what: sign-ins, configuration and secret changes, approvals, tool calls and scheduler fires. Newest first." />
      <React.Suspense fallback={<LoadingState rows={10} />}>
        <AuditLog />
      </React.Suspense>
    </PageContainer>
  );
}
