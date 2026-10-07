import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "@/lib/api/client";

type ExecutionStatus = Schemas["ExecutionStatus"];

export const executionKeys = {
  all: ["executions"] as const,
  list: (filters: { status?: ExecutionStatus[]; pipelineId?: string; offset: number }) => ["executions", "list", filters] as const,
  detail: (id: string) => ["executions", "detail", id] as const,
  events: (id: string) => ["executions", "events", id] as const,
};

export function useExecutions(filters: { status?: ExecutionStatus[]; pipelineId?: string; offset: number; limit?: number }) {
  return useQuery({
    queryKey: executionKeys.list(filters),
    queryFn: async () =>
      unwrap(
        await api.GET("/api/v1/executions", {
          params: { query: { status: filters.status, pipeline_id: filters.pipelineId, offset: filters.offset, limit: filters.limit ?? 50 } },
        }),
      ),
    placeholderData: keepPreviousData,
    refetchInterval: 10_000,
  });
}

export function useExecution(id: string) {
  return useQuery({
    queryKey: executionKeys.detail(id),
    queryFn: async () => unwrap(await api.GET("/api/v1/executions/{execution_id}", { params: { path: { execution_id: id } } })),
  });
}

export function useExecutionEvents(id: string) {
  return useQuery({
    queryKey: executionKeys.events(id),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/executions/{execution_id}/events", { params: { path: { execution_id: id }, query: { after_seq: 0, limit: 2000 } } })),
    staleTime: Infinity,
  });
}

export function useControlExecution(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (action: "pause" | "resume" | "cancel" | "retry") =>
      unwrap(await api.POST("/api/v1/executions/{execution_id}/control", { params: { path: { execution_id: id } }, body: { action } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: executionKeys.all }),
  });
}

export function useRestartExecution(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/executions/{execution_id}/restart", { params: { path: { execution_id: id } } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: executionKeys.all }),
  });
}
