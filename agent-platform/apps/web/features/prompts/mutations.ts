import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "@/lib/api/client";

import { promptKeys } from "./queries";

export function useCreatePrompt() {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: Schemas["PromptTemplateIn"]) => unwrap(await api.POST("/api/v1/prompts", { body })),
    onSuccess: (data) => {
      qc.setQueryData(promptKeys.detail(data.id), data);
      void qc.invalidateQueries({ queryKey: promptKeys.list });
    },
  });
}

export function useAddPromptVersion(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["PromptVersionIn"]) =>
      unwrap(await api.POST("/api/v1/prompts/{template_id}/versions", { params: { path: { template_id: id } }, body })),
    onSuccess: (data) => {
      qc.setQueryData(promptKeys.detail(id), data);
      void qc.invalidateQueries({ queryKey: promptKeys.list });
    },
  });
}

export function useDeletePrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.DELETE("/api/v1/prompts/{template_id}", { params: { path: { template_id: id } } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: promptKeys.list }),
  });
}
