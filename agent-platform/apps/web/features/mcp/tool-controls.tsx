"use client";

import * as React from "react";

import { Tooltip } from "@/components/ui/menus";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/toggles";

import { useUpdateTool } from "./mutations";
import { RISK_LEVELS, type RiskLevel, type Tool } from "./queries";

export const STALE_REASON = "This tool no longer exists on the server. Run discovery again before enabling it.";
const VIEWER_REASON = "Viewers cannot change tool policy.";

/** Wraps a disabled control so its tooltip still works on hover and keyboard focus. */
function WithReason({ reason, children }: { reason: string | null; children: React.ReactElement }) {
  if (!reason) return children;
  return (
    <Tooltip content={reason}>
      <span tabIndex={0} className="inline-flex rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25">
        {children}
      </span>
    </Tooltip>
  );
}

export type ToolFlag = "is_enabled" | "requires_approval" | "is_destructive";

const FLAG_LABEL: Record<ToolFlag, string> = {
  is_enabled: "Enabled",
  requires_approval: "Requires approval",
  is_destructive: "Destructive",
};

export function ToolSwitch({ tool, flag, canEdit, id }: { tool: Tool; flag: ToolFlag; canEdit: boolean; id?: string }) {
  const update = useUpdateTool();
  // A stale tool can be switched off, never on.
  const staleBlock = flag === "is_enabled" && tool.is_stale && !tool.is_enabled;
  const reason = !canEdit ? VIEWER_REASON : staleBlock ? STALE_REASON : null;
  return (
    <WithReason reason={reason}>
      <Switch
        id={id}
        checked={tool[flag]}
        disabled={!!reason}
        onCheckedChange={(v) => update.mutate({ id: tool.id, patch: { [flag]: v } })}
        aria-label={`${FLAG_LABEL[flag]}: ${tool.namespaced_name || tool.name}`}
      />
    </WithReason>
  );
}

export function RiskSelect({ tool, canEdit, idPrefix = "risk" }: { tool: Tool; canEdit: boolean; idPrefix?: string }) {
  const update = useUpdateTool();
  const id = `${idPrefix}-${tool.id}`;
  return (
    <div className="w-[104px]">
      <label htmlFor={id} className="sr-only">
        Risk level: {tool.namespaced_name || tool.name}
      </label>
      <Select
        id={id}
        size="sm"
        value={tool.risk_level}
        disabled={!canEdit}
        onValueChange={(v) => update.mutate({ id: tool.id, patch: { risk_level: v as RiskLevel } })}
        options={RISK_LEVELS}
      />
    </div>
  );
}
