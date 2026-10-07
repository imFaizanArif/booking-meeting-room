"use client";

import { ChevronDown, Search, X } from "lucide-react";
import * as React from "react";

import { controlClass } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/menus";
import { Checkbox } from "@/components/ui/toggles";
import { cn } from "@/lib/utils";

export interface MultiSelectOption {
  value: string;
  label: React.ReactNode;
  /** Plain text used for filtering and for the selected chips. */
  text: string;
  description?: React.ReactNode;
  disabled?: boolean;
}

interface MultiSelectProps {
  id?: string;
  value: string[];
  onChange: (value: string[]) => void;
  options: MultiSelectOption[];
  placeholder?: string;
  emptyText?: string;
  className?: string;
  "aria-invalid"?: boolean;
}

/**
 * Checkbox list in a popover with a filter box. Selected values render as removable chips
 * under the trigger. Values that are not among the options (e.g. stale ids) stay visible.
 */
export function MultiSelect({ id, value, onChange, options, placeholder = "Select", emptyText = "No options.", className, ...rest }: MultiSelectProps) {
  const [open, setOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const selected = new Set(value);
  const byValue = new Map(options.map((o) => [o.value, o]));
  const q = query.trim().toLowerCase();
  const visible = q ? options.filter((o) => o.text.toLowerCase().includes(q)) : options;

  function toggle(v: string) {
    onChange(selected.has(v) ? value.filter((x) => x !== v) : [...value, v]);
  }

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            id={id}
            type="button"
            aria-invalid={rest["aria-invalid"]}
            className={cn(controlClass, "flex h-8 items-center justify-between gap-2 text-left")}
          >
            <span className={cn("truncate", value.length === 0 && "text-fg-subtle")}>
              {value.length === 0 ? placeholder : `${value.length} selected`}
            </span>
            <ChevronDown className="size-3.5 shrink-0 text-fg-subtle" aria-hidden />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-[var(--radix-popover-trigger-width)] min-w-64 p-0">
          <div className="relative border-b border-border">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-fg-subtle" aria-hidden />
            <input
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter"
              aria-label="Filter options"
              className="h-8 w-full bg-transparent pl-8 pr-2 text-sm outline-none placeholder:text-fg-subtle"
            />
          </div>
          <ul role="listbox" aria-multiselectable className="scrollbar-thin max-h-64 overflow-y-auto p-1">
            {visible.length === 0 ? <li className="px-2 py-1.5 text-xs text-fg-muted">{emptyText}</li> : null}
            {visible.map((o) => (
              <li key={o.value} role="option" aria-selected={selected.has(o.value)}>
                <label className={cn("flex cursor-default items-start gap-2 rounded-sm px-2 py-1.5 hover:bg-subtle", o.disabled && "opacity-50")}>
                  <Checkbox className="mt-0.5" checked={selected.has(o.value)} disabled={o.disabled} onCheckedChange={() => toggle(o.value)} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm">{o.label}</span>
                    {o.description ? <span className="block text-xs text-fg-subtle">{o.description}</span> : null}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </PopoverContent>
      </Popover>
      {value.length ? (
        <ul className="flex flex-wrap gap-1" aria-label="Selected">
          {value.map((v) => (
            <li key={v} className="inline-flex h-6 max-w-full items-center gap-1 rounded-sm border border-border bg-subtle pl-1.5 pr-0.5 font-mono text-2xs text-fg">
              <span className={cn("truncate", !byValue.has(v) && "text-danger")} title={byValue.has(v) ? undefined : "Not available"}>
                {byValue.get(v)?.text ?? v}
              </span>
              <button type="button" onClick={() => toggle(v)} aria-label={`Remove ${byValue.get(v)?.text ?? v}`} className="rounded-sm p-0.5 text-fg-subtle hover:bg-muted hover:text-fg">
                <X className="size-3" />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
