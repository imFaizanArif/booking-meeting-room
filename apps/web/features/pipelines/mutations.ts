import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "@/lib/api/client";

import type { Graph } from "./graph";
import { pipelineKeys } from "./queries";

export type GraphIssue = Schemas["GraphIssueOut"];

/** Issues from a 422 save (`details.issues`). */
export function issuesFromError(error: unknown): GraphIssue[] {
  const details = (error as { details?: Record<string, unknown> } | null)?.details;
  const issues = details?.["issues"];
  return Array.isArray(issues) ? (issues as GraphIssue[]) : [];
}

export function useCreatePipeline() {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: { name: string; description?: string | null }) => unwrap(await api.POST("/api/v1/pipelines", { body })),
    onSuccess: (data) => {
      qc.setQueryData(pipelineKeys.detail(data.id), data);
      void qc.invalidateQueries({ queryKey: pipelineKeys.all });
    },
  });
}

export function useUpdatePipeline(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: Schemas["PipelinePatch"]) =>
      unwrap(await api.PATCH("/api/v1/pipelines/{pipeline_id}", { params: { path: { pipeline_id: id } }, body })),
    onSuccess: (data) => {
      qc.setQueryData(pipelineKeys.detail(id), data);
      void qc.invalidateQueries({ queryKey: pipelineKeys.all });
    },
  });
}

/** Archive/unarchive or delete from the list, where the id varies per row. */
export function useArchivePipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, archived }: { id: string; archived: boolean }) =>
      unwrap(await api.PATCH("/api/v1/pipelines/{pipeline_id}", { params: { path: { pipeline_id: id } }, body: { is_archived: archived } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: pipelineKeys.all }),
  });
}

export function useDeletePipeline() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.DELETE("/api/v1/pipelines/{pipeline_id}", { params: { path: { pipeline_id: id } } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: pipelineKeys.all }),
  });
}

export function useSaveVersion(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: { graph: Graph; change_note?: string | null }) =>
      unwrap(
        await api.POST("/api/v1/pipelines/{pipeline_id}/versions", {
          params: { path: { pipeline_id: id } },
          body: { graph: body.graph as unknown as Record<string, unknown>, change_note: body.change_note || null },
        }),
      ),
    onSuccess: (data) => {
      qc.setQueryData(pipelineKeys.detail(id), data);
      void qc.invalidateQueries({ queryKey: pipelineKeys.list(false) });
      void qc.invalidateQueries({ queryKey: pipelineKeys.list(true) });
    },
  });
}

export function useValidateGraph() {
  return useMutation({
    mutationFn: async (graph: Graph) =>
      unwrap(await api.POST("/api/v1/pipelines/validate", { body: graph as unknown as Record<string, unknown> })),
  });
}

export function useRunPipeline(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (input: Record<string, unknown>) =>
      unwrap(await api.POST("/api/v1/pipelines/{pipeline_id}/run", { params: { path: { pipeline_id: id } }, body: { input } })),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["executions"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
      void qc.invalidateQueries({ queryKey: pipelineKeys.all });
    },
  });
}
