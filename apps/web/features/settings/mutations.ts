import { useMutation, useQueryClient } from "@tanstack/react-query";

import { authKeys } from "@/features/auth/queries";
import { api, unwrap, type Schemas } from "@/lib/api/client";

import { settingsKeys } from "./queries";

export function useUpdateWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: Schemas["WorkspacePatch"]) => unwrap(await api.PATCH("/api/v1/workspace", { body })),
    onSuccess: (data) => qc.setQueryData(settingsKeys.workspace, data),
  });
}

export function useAddMember() {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: Schemas["MemberIn"]) => unwrap(await api.POST("/api/v1/members", { body })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: settingsKeys.members }),
  });
}

/** Role change. Errors (e.g. demoting the last owner, 422) are shown inline under the members table. */
export function useUpdateMemberRole() {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async ({ userId, role }: { userId: string; role: Schemas["Role"] }) =>
      unwrap(await api.PATCH("/api/v1/members/{user_id}", { params: { path: { user_id: userId } }, body: { role } })),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: settingsKeys.members });
      void qc.invalidateQueries({ queryKey: authKeys.me });
    },
  });
}

export function useSaveChannel() {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async ({ id, body }: { id?: string; body: Schemas["ChannelIn"] }) =>
      id
        ? unwrap(await api.PUT("/api/v1/notification-channels/{channel_id}", { params: { path: { channel_id: id } }, body }))
        : unwrap(await api.POST("/api/v1/notification-channels", { body })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: settingsKeys.channels });
      void qc.invalidateQueries({ queryKey: settingsKeys.secrets });
    },
  });
}

export function useDeleteChannel() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.DELETE("/api/v1/notification-channels/{channel_id}", { params: { path: { channel_id: id } } })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: settingsKeys.channels });
      void qc.invalidateQueries({ queryKey: settingsKeys.secrets });
    },
  });
}

export function useSaveVariable() {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: Schemas["PromptVariableIn"]) => unwrap(await api.PUT("/api/v1/prompt-variables", { body })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: settingsKeys.variables }),
  });
}

export function useDeleteVariable() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (key: string) => unwrap(await api.DELETE("/api/v1/prompt-variables/{key}", { params: { path: { key } } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: settingsKeys.variables }),
  });
}

/** Create or rotate: the API upserts by name and bumps the version. */
export function usePutSecret() {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: Schemas["SecretIn"]) => unwrap(await api.PUT("/api/v1/secrets", { body })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: settingsKeys.secrets }),
  });
}

export function useDeleteSecret() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.DELETE("/api/v1/secrets/{secret_id}", { params: { path: { secret_id: id } } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: settingsKeys.secrets }),
  });
}
