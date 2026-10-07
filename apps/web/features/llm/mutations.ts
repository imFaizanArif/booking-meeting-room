import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "@/lib/api/client";

import { llmKeys, type Model, type Provider } from "./queries";

function useInvalidateLlm() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: llmKeys.all });
}

// ---- providers ------------------------------------------------------------------------------

export function useCreateProvider() {
  const invalidate = useInvalidateLlm();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: Schemas["ProviderIn"]) => unwrap(await api.POST("/api/v1/llm/providers", { body })),
    onSuccess: () => void invalidate(),
  });
}

export function useUpdateProvider() {
  const invalidate = useInvalidateLlm();
  return useMutation({
    meta: { silent: true },
    mutationFn: async ({ id, body }: { id: string; body: Schemas["ProviderPatch"] }) =>
      unwrap(await api.PATCH("/api/v1/llm/providers/{provider_id}", { params: { path: { provider_id: id } }, body })),
    onSuccess: () => void invalidate(),
  });
}

/** Toggle `is_active` from the table. Optimistic, rolled back on error (the toast explains why). */
export function useSetProviderActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) =>
      unwrap(await api.PATCH("/api/v1/llm/providers/{provider_id}", { params: { path: { provider_id: id } }, body: { is_active, clear_api_key: false } })),
    onMutate: async ({ id, is_active }) => {
      await qc.cancelQueries({ queryKey: llmKeys.providers });
      const previous = qc.getQueryData<Provider[]>(llmKeys.providers);
      qc.setQueryData<Provider[]>(llmKeys.providers, (rows) => rows?.map((p) => (p.id === id ? { ...p, is_active } : p)));
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(llmKeys.providers, ctx.previous);
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: llmKeys.all }),
  });
}

export function useDeleteProvider() {
  const invalidate = useInvalidateLlm();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.DELETE("/api/v1/llm/providers/{provider_id}", { params: { path: { provider_id: id } } })),
    onSuccess: () => void invalidate(),
  });
}

/** The result is shown inline in the row, so errors are not toasted. */
export function useTestProvider() {
  const invalidate = useInvalidateLlm();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (id: string) => unwrap(await api.POST("/api/v1/llm/providers/{provider_id}/test", { params: { path: { provider_id: id } } })),
    onSettled: () => void invalidate(),
  });
}

// ---- models ---------------------------------------------------------------------------------

export function useCreateModel() {
  const invalidate = useInvalidateLlm();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: Schemas["ModelIn"]) => unwrap(await api.POST("/api/v1/llm/models", { body })),
    onSuccess: () => void invalidate(),
  });
}

export function useUpdateModel() {
  const invalidate = useInvalidateLlm();
  return useMutation({
    meta: { silent: true },
    mutationFn: async ({ id, body }: { id: string; body: Schemas["ModelPatch"] }) =>
      unwrap(await api.PATCH("/api/v1/llm/models/{model_id}", { params: { path: { model_id: id } }, body })),
    onSuccess: () => void invalidate(),
  });
}

export function useSetModelActive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, is_active }: { id: string; is_active: boolean }) =>
      unwrap(await api.PATCH("/api/v1/llm/models/{model_id}", { params: { path: { model_id: id } }, body: { is_active } })),
    onMutate: async ({ id, is_active }) => {
      await qc.cancelQueries({ queryKey: llmKeys.models });
      const previous = qc.getQueryData<Model[]>(llmKeys.models);
      qc.setQueryData<Model[]>(llmKeys.models, (rows) => rows?.map((m) => (m.id === id ? { ...m, is_active } : m)));
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(llmKeys.models, ctx.previous);
    },
    onSettled: () => void qc.invalidateQueries({ queryKey: llmKeys.models }),
  });
}

export function useSetDefaultModel() {
  const invalidate = useInvalidateLlm();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.POST("/api/v1/llm/models/{model_id}/default", { params: { path: { model_id: id } } })),
    onSuccess: () => void invalidate(),
  });
}

export function useDeleteModel() {
  const invalidate = useInvalidateLlm();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.DELETE("/api/v1/llm/models/{model_id}", { params: { path: { model_id: id } } })),
    onSuccess: () => void invalidate(),
  });
}
