import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";

export const AUDIT_EVENT_TYPES = [
  "auth.login",
  "auth.login_failed",
  "auth.logout",
  "config.created",
  "config.updated",
  "config.deleted",
  "secret.written",
  "secret.accessed",
  "secret.deleted",
  "execution.started",
  "execution.control",
  "approval.decided",
  "tool.executed",
  "tool.denied",
  "member.updated",
  "schedule.fired",
] as const;

export const AUDIT_ENTITY_TYPES = [
  "approval",
  "execution",
  "llm_model",
  "llm_provider",
  "mcp_server",
  "mcp_tool",
  "notification_channel",
  "pipeline",
  "prompt_template",
  "prompt_variable",
  "schedule",
  "secret",
  "tool_call",
  "user",
  "workspace",
] as const;

export interface AuditFilters {
  q?: string;
  event_type?: string;
  entity_type?: string;
  actor?: string;
  /** datetime-local values ("2026-10-06T09:30"), interpreted in the viewer's timezone. */
  since?: string;
  until?: string;
  offset: number;
}

export const AUDIT_PAGE_SIZE = 50;

function toIso(local: string | undefined): string | undefined {
  if (!local) return undefined;
  const d = new Date(local);
  return Number.isNaN(d.getTime()) ? undefined : d.toISOString();
}

export function useAuditLog(filters: AuditFilters) {
  return useQuery({
    queryKey: ["audit", "list", filters] as const,
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/audit", {
          params: {
            query: {
              q: filters.q || undefined,
              event_type: filters.event_type || undefined,
              entity_type: filters.entity_type || undefined,
              actor: filters.actor || undefined,
              since: toIso(filters.since),
              until: toIso(filters.until),
              limit: AUDIT_PAGE_SIZE,
              offset: filters.offset,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}
