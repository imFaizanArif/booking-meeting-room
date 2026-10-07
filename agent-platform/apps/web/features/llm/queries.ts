import { useQuery } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "@/lib/api/client";

export type Provider = Schemas["ProviderOut"];
export type Model = Schemas["ModelOut"];
export type ProviderType = Schemas["ProviderType"];

export const llmKeys = {
  all: ["llm"] as const,
  providers: ["llm", "providers"] as const,
  models: ["llm", "models"] as const,
};

export function useProviders() {
  return useQuery({
    queryKey: llmKeys.providers,
    queryFn: async () => unwrap(await api.GET("/api/v1/llm/providers")),
  });
}

export function useModels() {
  return useQuery({
    queryKey: llmKeys.models,
    queryFn: async () => unwrap(await api.GET("/api/v1/llm/models")),
  });
}

export const PROVIDER_TYPES: { value: ProviderType; label: string; description: string }[] = [
  { value: "openai", label: "OpenAI", description: "OpenAI or any OpenAI-compatible endpoint" },
  { value: "anthropic", label: "Anthropic", description: "Anthropic Messages API" },
  { value: "ollama", label: "Ollama", description: "Local models, no key needed" },
  { value: "fake", label: "Fake", description: "Offline deterministic responses for testing" },
];

/** Provider types that work without an API key (mirrors the backend's KEYLESS set). */
export const KEYLESS: ReadonlySet<ProviderType> = new Set<ProviderType>(["ollama", "fake"]);

export function providerTypeLabel(type: ProviderType | null | undefined): string {
  return PROVIDER_TYPES.find((t) => t.value === type)?.label ?? type ?? "—";
}
