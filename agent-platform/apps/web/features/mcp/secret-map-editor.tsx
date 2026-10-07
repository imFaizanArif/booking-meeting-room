"use client";

import { Plus, Undo2, X } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { maskedHint } from "@/components/ui-extra/secret-state";
import { cn } from "@/lib/utils";

export type SecretMode = "keep" | "replace" | "remove";

/** One row of an env or headers map. Existing values are never known to the client. */
export interface SecretRow {
  rowId: string;
  name: string;
  value: string;
  existing: boolean;
  mode: SecretMode;
  hint?: string | null;
}

export interface SecretRowError {
  name?: string;
  value?: string;
}

let seq = 0;
export function newRowId(): string {
  seq += 1;
  return `row-${seq}`;
}

export function rowsFromState(state: Record<string, { is_set: boolean; hint?: string | null }> | undefined): SecretRow[] {
  return Object.entries(state ?? {})
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, s]) => ({ rowId: newRowId(), name, value: "", existing: true, mode: "keep" as const, hint: s.hint }));
}

/** Build the write-only payload: new values for new/replaced rows, names to keep for the rest. Removed rows are omitted. */
export function rowsToPayload(rows: SecretRow[]): { values: Record<string, string>; keep: string[] } {
  const values: Record<string, string> = {};
  const keep: string[] = [];
  for (const r of rows) {
    const name = r.name.trim();
    if (!name) continue;
    if (!r.existing) values[name] = r.value;
    else if (r.mode === "replace") values[name] = r.value;
    else if (r.mode === "keep") keep.push(name);
  }
  return { values, keep };
}

/** Per-row validation, index-aligned with `rows`. Returns null when everything is valid. */
export function validateRows(rows: SecretRow[], kind: "env" | "headers"): (SecretRowError | undefined)[] | null {
  const pattern = kind === "env" ? /^[A-Za-z_][A-Za-z0-9_]*$/ : /^[A-Za-z0-9!#$%&'*+.^_`|~-]+$/;
  const seen = new Map<string, number>();
  let failed = false;
  const out = rows.map((r, i) => {
    const err: SecretRowError = {};
    const name = r.name.trim();
    const live = !(r.existing && r.mode === "remove");
    if (!r.existing) {
      if (!name) err.name = "Enter a name";
      else if (!pattern.test(name)) err.name = kind === "env" ? "Letters, digits and _ only; cannot start with a digit" : "Not a valid header name";
    }
    if (live && name) {
      const key = kind === "headers" ? name.toLowerCase() : name;
      if (seen.has(key)) err.name = "Duplicate name";
      seen.set(key, i);
    }
    if ((!r.existing || r.mode === "replace") && r.value === "") err.value = "Enter a value";
    if (err.name || err.value) {
      failed = true;
      return err;
    }
    return undefined;
  });
  return failed ? out : null;
}

const MODE_OPTIONS = [
  { value: "keep", label: "Keep" },
  { value: "replace", label: "Replace" },
  { value: "remove", label: "Remove" },
];

export function SecretMapEditor({
  kind,
  rows,
  onChange,
  errors,
  idPrefix,
}: {
  kind: "env" | "headers";
  rows: SecretRow[];
  onChange: (rows: SecretRow[]) => void;
  errors?: (SecretRowError | undefined)[] | null;
  idPrefix: string;
}) {
  const noun = kind === "env" ? "variable" : "header";
  const update = (rowId: string, patch: Partial<SecretRow>) => onChange(rows.map((r) => (r.rowId === rowId ? { ...r, ...patch } : r)));

  return (
    <div className="flex flex-col gap-1.5">
      {rows.length === 0 ? <p className="text-xs text-fg-subtle">No {kind === "env" ? "environment variables" : "headers"}.</p> : null}
      {rows.map((r, i) => {
        const err = errors?.[i];
        const removed = r.existing && r.mode === "remove";
        return (
          <div key={r.rowId} className="flex flex-col gap-0.5">
            <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,3fr)_auto] items-center gap-1.5">
              {r.existing ? (
                <span
                  className={cn("truncate px-0.5 font-mono text-xs", removed ? "text-fg-subtle line-through" : "text-fg")}
                  title={r.name}
                >
                  {r.name}
                </span>
              ) : (
                <Input
                  value={r.name}
                  onChange={(e) => update(r.rowId, { name: e.target.value })}
                  placeholder={kind === "env" ? "NAME" : "Authorization"}
                  aria-label={`${kind === "env" ? "Variable" : "Header"} name ${i + 1}`}
                  aria-invalid={!!err?.name}
                  spellCheck={false}
                  className="h-7 font-mono text-xs"
                />
              )}
              {r.existing && r.mode !== "replace" ? (
                <div className="flex h-7 min-w-0 items-center gap-2">
                  {removed ? (
                    <Badge tone="danger">Will be removed</Badge>
                  ) : (
                    <span className="truncate text-xs text-fg-muted">
                      Set <span className="font-mono text-fg">{maskedHint(r.hint)}</span>
                    </span>
                  )}
                </div>
              ) : (
                <Input
                  type="password"
                  autoComplete="new-password"
                  value={r.value}
                  onChange={(e) => update(r.rowId, { value: e.target.value })}
                  placeholder={r.existing ? "New value" : "Value"}
                  aria-label={`Value for ${r.name || `${noun} ${i + 1}`}`}
                  aria-invalid={!!err?.value}
                  spellCheck={false}
                  className="h-7 font-mono text-xs"
                />
              )}
              {r.existing ? (
                <div className="w-[104px]">
                  <label htmlFor={`${idPrefix}-${r.rowId}-mode`} className="sr-only">
                    What to do with {r.name}
                  </label>
                  <Select
                    id={`${idPrefix}-${r.rowId}-mode`}
                    size="sm"
                    value={r.mode}
                    onValueChange={(mode) => update(r.rowId, { mode: mode as SecretMode, value: "" })}
                    options={MODE_OPTIONS}
                  />
                </div>
              ) : (
                <div className="flex w-[104px] justify-end">
                  <Button type="button" size="icon" variant="ghost" aria-label={`Remove ${r.name || `new ${noun}`}`} onClick={() => onChange(rows.filter((x) => x.rowId !== r.rowId))}>
                    <X />
                  </Button>
                </div>
              )}
            </div>
            {err?.name || err?.value ? (
              <p role="alert" className="text-xs text-danger">
                {[err.name, err.value].filter(Boolean).join(". ")}
              </p>
            ) : null}
          </div>
        );
      })}
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="-ml-2 self-start"
          onClick={() => onChange([...rows, { rowId: newRowId(), name: "", value: "", existing: false, mode: "replace" }])}
        >
          <Plus /> Add {noun}
        </Button>
        {rows.some((r) => r.existing && r.mode !== "keep") ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => onChange(rows.map((r) => (r.existing ? { ...r, mode: "keep" as const, value: "" } : r)))}
          >
            <Undo2 /> Keep all stored values
          </Button>
        ) : null}
      </div>
    </div>
  );
}
