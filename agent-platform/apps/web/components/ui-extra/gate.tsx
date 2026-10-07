"use client";

import * as React from "react";

import { Tooltip } from "@/components/ui/menus";

/**
 * Cosmetic permission gate. When `allowed` is false the child control is rendered
 * disabled and wrapped so the tooltip still opens on hover and focus (disabled
 * buttons swallow pointer events). The backend enforces the real permission.
 */
export function Gate({ allowed, reason, children }: { allowed: boolean; reason: string; children: React.ReactElement<{ disabled?: boolean }> }) {
  if (allowed) return children;
  return (
    <Tooltip content={reason}>
      <span tabIndex={0} className="inline-flex cursor-not-allowed rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25">
        {React.cloneElement(children, { disabled: true })}
      </span>
    </Tooltip>
  );
}
