import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";

export const pipelineKeys = {
  all: ["pipelines"] as const,
  list: (includeArchived: boolean) => ["pipelines", "list", includeArchived] as const,
  detail: (id: string) => ["pipelines", "detail", id] as const,
  version: (id: string, version: number) => ["pipelines", "version", id, version] as const,
  nodeTypes: ["node-types"] as const,
  models: ["llm", "models"] as const,
  tools: ["mcp", "tools"] as const,
  channels: ["notification-channels"] as const,
};

export function usePipelines(includeArchived = false) {
  return useQuery({
    queryKey: pipelineKeys.list(includeArchived),
    queryFn: async () => unwrap(await api.GET("/api/v1/pipelines", { params: { query: { include_archived: includeArchived } } })),
  });
}

export function usePipeline(id: string | undefined) {
  return useQuery({
    queryKey: pipelineKeys.detail(id ?? ""),
    queryFn: async () => unwrap(await api.GET("/api/v1/pipelines/{pipeline_id}", { params: { path: { pipeline_id: id! } } })),
    enabled: !!id,
    refetchOnWindowFocus: false,
  });
}

export function usePipelineVersion(id: string, version: number | null | undefined) {
  return useQuery({
    queryKey: pipelineKeys.version(id, version ?? 0),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/pipelines/{pipeline_id}/versions/{version}", { params: { path: { pipeline_id: id, version: version! } } })),
    enabled: !!id && version != null,
    staleTime: Infinity, // versions are immutable
  });
}

export function useNodeTypes() {
  return useQuery({
    queryKey: pipelineKeys.nodeTypes,
    queryFn: async () => unwrap(await api.GET("/api/v1/node-types")),
    staleTime: Infinity,
  });
}

export function useModels() {
  return useQuery({ queryKey: pipelineKeys.models, queryFn: async () => unwrap(await api.GET("/api/v1/llm/models")), staleTime: 60_000 });
}

export function useTools() {
  return useQuery({ queryKey: pipelineKeys.tools, queryFn: async () => unwrap(await api.GET("/api/v1/mcp/tools")), staleTime: 60_000 });
}

export function useChannels(enabled = true) {
  return useQuery({
    queryKey: pipelineKeys.channels,
    queryFn: async () => unwrap(await api.GET("/api/v1/notification-channels")),
    staleTime: 60_000,
    enabled,
  });
}
