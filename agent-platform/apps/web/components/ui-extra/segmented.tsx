"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

export interface SegmentedOption<V extends string> {
  value: V;
  label: React.ReactNode;
}

interface SegmentedControlProps<V extends string> {
  value: V;
  onValueChange: (value: V) => void;
  options: SegmentedOption<V>[];
  id?: string;
  "aria-label"?: string;
  "aria-labelledby"?: string;
  disabled?: boolean;
  className?: string;
}

/**
 * Small single-choice control (radio group semantics). Arrow keys move the selection,
 * only the selected segment is in the tab order.
 */
export function SegmentedControl<V extends string>({ value, onValueChange, options, id, disabled, className, ...aria }: SegmentedControlProps<V>) {
  const refs = React.useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    const delta = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!delta) return;
    e.preventDefault();
    const next = (index + delta + options.length) % options.length;
    onValueChange(options[next]!.value);
    refs.current[next]?.focus();
  }

  return (
    <div
      id={id}
      role="radiogroup"
      aria-label={aria["aria-label"]}
      aria-labelledby={aria["aria-labelledby"]}
      className={cn("inline-flex h-8 items-center gap-0.5 rounded-md border border-border-strong bg-subtle p-0.5", className)}
    >
      {options.map((opt, i) => {
        const active = opt.value === value;
        return (
          <button
            key={opt.value}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={active}
            tabIndex={active ? 0 : -1}
            disabled={disabled}
            onClick={() => onValueChange(opt.value)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={cn(
              "h-full rounded-sm px-2.5 text-xs font-medium text-fg-muted transition-colors duration-100",
              "hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 disabled:opacity-50",
              active && "bg-surface text-fg shadow-[0_1px_0_0_var(--border)]",
            )}
          >
            {opt.label}
          </button>
        );
      })}
    </div>
  );
}
