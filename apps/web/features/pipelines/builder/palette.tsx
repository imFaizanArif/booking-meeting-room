"use client";

import * as React from "react";

import type { Schemas } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import type { NodeType } from "../graph";
import { NODE_ICONS, PALETTE_GROUPS } from "../node-meta";
import { NODE_DRAG_MIME } from "./canvas";

/** Node palette: drag onto the canvas, or click to add next to the selection. */
export function NodePalette({ nodeTypes, onAdd, disabled }: {
  nodeTypes: Record<string, Schemas["NodeTypeOut"]>;
  onAdd: (type: NodeType) => void;
  disabled?: boolean;
}) {
  return (
    <aside className="scrollbar-thin flex w-[172px] shrink-0 flex-col overflow-y-auto border-r border-border bg-surface" aria-label="Node palette">
      <p className="px-3 pb-1 pt-3 text-2xs text-fg-subtle">Drag onto the canvas, or click to add after the selected node.</p>
      {PALETTE_GROUPS.map((group) => (
        <div key={group.label} className="px-2 pb-2 pt-2">
          <p className="px-1 pb-1 text-2xs font-medium uppercase tracking-[0.06em] text-fg-subtle">{group.label}</p>
          <ul className="flex flex-col gap-px">
            {group.types.map((type) => {
              const info = nodeTypes[type];
              const Icon = NODE_ICONS[type];
              return (
                <li key={type}>
                  <button
                    type="button"
                    draggable={!disabled}
                    disabled={disabled}
                    onDragStart={(e) => {
                      e.dataTransfer.setData(NODE_DRAG_MIME, type);
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    onClick={() => onAdd(type)}
                    title={info?.description}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-2 py-1 text-left transition-colors duration-100 hover:bg-subtle",
                      "cursor-grab active:cursor-grabbing disabled:cursor-not-allowed disabled:opacity-50",
                    )}
                  >
                    <Icon className="mt-0.5 size-3.5 shrink-0 text-fg-muted" aria-hidden />
                    <span className="truncate text-sm">{info?.label ?? type}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </aside>
  );
}
