"use client";

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Search } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

import { Button } from "./button";
import { Input } from "./input";
import { Checkbox } from "./toggles";

export interface Column<T> {
  id: string;
  header: React.ReactNode;
  cell: (row: T) => React.ReactNode;
  sortValue?: (row: T) => string | number | null | undefined;
  className?: string;
  headerClassName?: string;
  align?: "left" | "right";
}

interface ServerPaging {
  total: number;
  limit: number;
  offset: number;
  onOffsetChange: (offset: number) => void;
}

interface DataTableProps<T> {
  rows: T[];
  columns: Column<T>[];
  getRowId: (row: T) => string;
  onRowClick?: (row: T) => void;
  searchText?: (row: T) => string;
  searchPlaceholder?: string;
  toolbar?: React.ReactNode;
  empty?: React.ReactNode;
  pageSize?: number;
  server?: ServerPaging;
  selectable?: boolean;
  selected?: Set<string>;
  onSelectedChange?: (ids: Set<string>) => void;
  initialSort?: { id: string; desc: boolean };
  className?: string;
  rowClassName?: (row: T) => string | undefined;
}

export function DataTable<T>({
  rows,
  columns,
  getRowId,
  onRowClick,
  searchText,
  searchPlaceholder = "Filter",
  toolbar,
  empty,
  pageSize = 25,
  server,
  selectable,
  selected,
  onSelectedChange,
  initialSort,
  className,
  rowClassName,
}: DataTableProps<T>) {
  const [query, setQuery] = React.useState("");
  const [sort, setSort] = React.useState(initialSort ?? null);
  const [page, setPage] = React.useState(0);

  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    let out = q && searchText ? rows.filter((r) => searchText(r).toLowerCase().includes(q)) : rows;
    const col = sort ? columns.find((c) => c.id === sort.id) : undefined;
    if (col?.sortValue) {
      const value = col.sortValue;
      out = [...out].sort((a, b) => {
        const av = value(a) ?? "";
        const bv = value(b) ?? "";
        const cmp = av < bv ? -1 : av > bv ? 1 : 0;
        return sort?.desc ? -cmp : cmp;
      });
    }
    return out;
  }, [rows, query, sort, columns, searchText]);

  const [pageQuery, setPageQuery] = React.useState(query);
  if (pageQuery !== query) {
    setPageQuery(query);
    setPage(0);
  }

  const visible = server ? filtered : filtered.slice(page * pageSize, (page + 1) * pageSize);
  const total = server ? server.total : filtered.length;
  const offset = server ? server.offset : page * pageSize;
  const limit = server ? server.limit : pageSize;
  const allIds = visible.map(getRowId);
  const allChecked = selectable && allIds.length > 0 && allIds.every((id) => selected?.has(id));
  const someChecked = selectable && allIds.some((id) => selected?.has(id));

  function toggleSort(col: Column<T>) {
    if (!col.sortValue) return;
    setSort((s) => (s?.id === col.id ? (s.desc ? null : { id: col.id, desc: true }) : { id: col.id, desc: false }));
  }

  function toggleRow(id: string) {
    if (!onSelectedChange) return;
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    onSelectedChange(next);
  }

  function toggleAll() {
    if (!onSelectedChange) return;
    const next = new Set(selected);
    if (allChecked) allIds.forEach((id) => next.delete(id));
    else allIds.forEach((id) => next.add(id));
    onSelectedChange(next);
  }

  return (
    <div className={cn("flex flex-col gap-2", className)}>
      {searchText || toolbar ? (
        <div className="flex flex-wrap items-center gap-2">
          {searchText ? (
            <div className="relative w-64 max-w-full">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" aria-hidden />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={searchPlaceholder}
                aria-label={searchPlaceholder}
                className="h-7 pl-8 text-xs"
              />
            </div>
          ) : null}
          {toolbar}
        </div>
      ) : null}
      <div className="scrollbar-thin overflow-x-auto rounded-md border border-border bg-surface">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border bg-subtle text-left">
              {selectable ? (
                <th className="w-8 px-3 py-1.5">
                  <Checkbox
                    aria-label="Select all rows"
                    checked={allChecked ? true : someChecked ? "indeterminate" : false}
                    onCheckedChange={toggleAll}
                  />
                </th>
              ) : null}
              {columns.map((col) => {
                const active = sort?.id === col.id;
                return (
                  <th
                    key={col.id}
                    scope="col"
                    aria-sort={active ? (sort?.desc ? "descending" : "ascending") : undefined}
                    className={cn(
                      "whitespace-nowrap px-3 py-1.5 text-xs font-medium text-fg-muted",
                      col.align === "right" && "text-right",
                      col.headerClassName,
                    )}
                  >
                    {col.sortValue ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(col)}
                        className={cn("inline-flex items-center gap-1 hover:text-fg", active && "text-fg")}
                      >
                        {col.header}
                        {active ? sort?.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" /> : null}
                      </button>
                    ) : (
                      col.header
                    )}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={columns.length + (selectable ? 1 : 0)} className="px-3 py-6 text-center text-sm text-fg-muted">
                  {empty ?? (query ? "No rows match this filter." : "Nothing here yet.")}
                </td>
              </tr>
            ) : (
              visible.map((row) => {
                const id = getRowId(row);
                return (
                  <tr
                    key={id}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    className={cn(
                      "border-b border-border last:border-b-0",
                      onRowClick && "cursor-pointer hover:bg-subtle",
                      selected?.has(id) && "bg-subtle",
                      rowClassName?.(row),
                    )}
                  >
                    {selectable ? (
                      <td className="w-8 px-3 py-2" onClick={(e) => e.stopPropagation()}>
                        <Checkbox aria-label="Select row" checked={selected?.has(id) ?? false} onCheckedChange={() => toggleRow(id)} />
                      </td>
                    ) : null}
                    {columns.map((col) => (
                      <td key={col.id} className={cn("px-3 py-2 align-middle", col.align === "right" && "text-right tabular", col.className)}>
                        {col.cell(row)}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {total > limit ? (
        <div className="flex items-center justify-between text-xs text-fg-muted">
          <span className="tabular">
            {offset + 1}–{Math.min(offset + limit, total)} of {total}
          </span>
          <div className="flex gap-1">
            <Button
              size="icon"
              variant="ghost"
              aria-label="Previous page"
              disabled={offset === 0}
              onClick={() => (server ? server.onOffsetChange(Math.max(0, offset - limit)) : setPage((p) => p - 1))}
            >
              <ChevronLeft />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              aria-label="Next page"
              disabled={offset + limit >= total}
              onClick={() => (server ? server.onOffsetChange(offset + limit) : setPage((p) => p + 1))}
            >
              <ChevronRight />
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
