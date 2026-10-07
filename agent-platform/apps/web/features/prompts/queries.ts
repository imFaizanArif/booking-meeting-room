import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";

export const promptKeys = {
  all: ["prompts"] as const,
  list: ["prompts", "list"] as const,
  detail: (id: string) => ["prompts", "detail", id] as const,
  preview: (body: string, sample: string) => ["prompts", "preview", body, sample] as const,
  variables: ["prompt-variables"] as const,
};

export function usePromptTemplates() {
  return useQuery({ queryKey: promptKeys.list, queryFn: async () => unwrap(await api.GET("/api/v1/prompts")) });
}

export function usePromptTemplate(id: string | null | undefined) {
  return useQuery({
    queryKey: promptKeys.detail(id ?? ""),
    queryFn: async () => unwrap(await api.GET("/api/v1/prompts/{template_id}", { params: { path: { template_id: id! } } })),
    enabled: !!id,
    refetchOnWindowFocus: false,
  });
}

export function usePromptVariables() {
  return useQuery({ queryKey: promptKeys.variables, queryFn: async () => unwrap(await api.GET("/api/v1/prompt-variables")), staleTime: 30_000 });
}

/** Server-rendered preview. `sample` is the raw JSON text; invalid JSON disables the query. */
export function usePromptPreview(body: string, sampleText: string, enabled = true) {
  let sample: Record<string, unknown> | null = null;
  try {
    const parsed: unknown = JSON.parse(sampleText || "{}");
    sample = parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null;
  } catch {
    sample = null;
  }
  return useQuery({
    queryKey: promptKeys.preview(body, sampleText),
    queryFn: async () => unwrap(await api.POST("/api/v1/prompts/preview", { body: { body, sample: sample ?? {} } })),
    enabled: enabled && sample !== null,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    retry: false,
  });
}
