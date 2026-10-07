import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";

export const settingsKeys = {
  workspace: ["settings", "workspace"] as const,
  members: ["settings", "members"] as const,
  channels: ["settings", "channels"] as const,
  variables: ["prompt-variables"] as const,
  secrets: ["settings", "secrets"] as const,
};

export function useWorkspace() {
  return useQuery({ queryKey: settingsKeys.workspace, queryFn: async () => unwrap(await api.GET("/api/v1/workspace")) });
}

export function useMembers() {
  return useQuery({ queryKey: settingsKeys.members, queryFn: async () => unwrap(await api.GET("/api/v1/members")) });
}

export function useChannels() {
  return useQuery({ queryKey: settingsKeys.channels, queryFn: async () => unwrap(await api.GET("/api/v1/notification-channels")) });
}

export function usePromptVariables() {
  return useQuery({ queryKey: settingsKeys.variables, queryFn: async () => unwrap(await api.GET("/api/v1/prompt-variables")) });
}

/** Owners only: the endpoint returns 403 for everyone else, so do not ask. */
export function useSecrets(enabled: boolean) {
  return useQuery({ queryKey: settingsKeys.secrets, queryFn: async () => unwrap(await api.GET("/api/v1/secrets")), enabled });
}

/** Notification events a channel can subscribe to. */
export const CHANNEL_EVENTS = [
  { value: "approval.created", label: "Approval needed", description: "An execution paused for a human decision." },
  { value: "pipeline.notification", label: "Pipeline notify node", description: "A Notify node in a pipeline sent a message." },
] as const;
