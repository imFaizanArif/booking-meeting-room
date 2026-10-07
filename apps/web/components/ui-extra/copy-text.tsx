"use client";

import { Copy } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { cn } from "@/lib/utils";

/** Monospace value that copies itself to the clipboard on click. Stops row-click propagation. */
export function CopyText({ value, display, label = "Value", className }: { value: string; display?: React.ReactNode; label?: string; className?: string }) {
  async function copy(e: React.MouseEvent) {
    e.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      toast.success(`${label} copied`);
    } catch {
      toast.error(`Could not copy ${label.toLowerCase()}`);
    }
  }
  return (
    <button
      type="button"
      onClick={copy}
      title={`Copy ${label.toLowerCase()}`}
      aria-label={`Copy ${label.toLowerCase()} ${value}`}
      className={cn(
        "group inline-flex max-w-full items-center gap-1 rounded-sm font-mono text-xs text-fg-muted hover:text-fg",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25",
        className,
      )}
    >
      <span className="truncate">{display ?? value}</span>
      <Copy className="size-3 shrink-0 opacity-0 transition-opacity duration-100 group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden />
    </button>
  );
}
