"use client";

import { ChevronRight } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

function Leaf({ value }: { value: unknown }) {
  if (value === null) return <span className="text-fg-subtle">null</span>;
  if (typeof value === "string") return <span className="text-ok whitespace-pre-wrap [overflow-wrap:anywhere]">&quot;{value}&quot;</span>;
  if (typeof value === "number") return <span className="text-info tabular">{value}</span>;
  if (typeof value === "boolean") return <span className="text-warn">{String(value)}</span>;
  return <span>{String(value)}</span>;
}

function Node({ name, value, depth, defaultOpen }: { name?: string; value: unknown; depth: number; defaultOpen: number }) {
  const isObject = value !== null && typeof value === "object";
  const [open, setOpen] = React.useState(depth < defaultOpen);
  const label = name !== undefined ? <span className="text-fg-muted">{name}: </span> : null;
  if (!isObject) {
    return (
      <div className="py-px" style={{ paddingLeft: depth * 14 }}>
        {label}
        <Leaf value={value} />
      </div>
    );
  }
  const entries = Array.isArray(value) ? value.map((v, i) => [String(i), v] as const) : Object.entries(value as Record<string, unknown>);
  const brackets = Array.isArray(value) ? ["[", "]"] : ["{", "}"];
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center py-px text-left hover:bg-subtle"
        style={{ paddingLeft: depth * 14 }}
        aria-expanded={open}
      >
        <ChevronRight className={cn("mr-0.5 size-3 text-fg-subtle transition-transform duration-100", open && "rotate-90")} />
        {label}
        <span className="text-fg-subtle">
          {brackets[0]}
          {open ? "" : ` ${entries.length} ${Array.isArray(value) ? "items" : "keys"} ${brackets[1]}`}
        </span>
      </button>
      {open ? (
        <>
          {entries.map(([k, v]) => (
            <Node key={k} name={Array.isArray(value) ? undefined : k} value={v} depth={depth + 1} defaultOpen={defaultOpen} />
          ))}
          <div className="text-fg-subtle" style={{ paddingLeft: depth * 14 + 14 }}>
            {brackets[1]}
          </div>
        </>
      ) : null}
    </div>
  );
}

export function JsonViewer({ value, className, defaultOpen = 2 }: { value: unknown; className?: string; defaultOpen?: number }) {
  return (
    <div className={cn("scrollbar-thin overflow-auto rounded-md border border-border bg-subtle p-2 font-mono text-xs leading-5", className)}>
      <Node value={value} depth={0} defaultOpen={defaultOpen} />
    </div>
  );
}
