import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "@/lib/api/client";

import { mcpKeys, type Tool } from "./queries";

function useInvalidateMcp() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: mcpKeys.all });
}

// ---- servers --------------------------------------------------------------------------------

export function useCreateServer() {
  const invalidate = useInvalidateMcp();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: Schemas["MCPServerIn"]) => unwrap(await api.POST("/api/v1/mcp/servers", { body })),
    onSuccess: () => void invalidate(),
  });
}

/** Full replacement (PUT). Secrets: `env`/`headers` carry new values, `*_keep` lists names to keep. */
export function useUpdateServer() {
  const invalidate = useInvalidateMcp();
  return useMutation({
    meta: { silent: true },
    mutationFn: async ({ id, body }: { id: string; body: Schemas["MCPServerIn"] }) =>
      unwrap(await api.PUT("/api/v1/mcp/servers/{server_id}", { params: { path: { server_id: id } }, body })),
    onSuccess: () => void invalidate(),
  });
}

export function useDeleteServer() {
  const invalidate = useInvalidateMcp();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.DELETE("/api/v1/mcp/servers/{server_id}", { params: { path: { server_id: id } } })),
    onSuccess: () => void invalidate(),
  });
}

export function useTestServer() {
  const invalidate = useInvalidateMcp();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.POST("/api/v1/mcp/servers/{server_id}/test", { params: { path: { server_id: id } } })),
    onSettled: () => void invalidate(),
  });
}

export function useReconnectServer() {
  const invalidate = useInvalidateMcp();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.POST("/api/v1/mcp/servers/{server_id}/reconnect", { params: { path: { server_id: id } } })),
    onSettled: () => void invalidate(),
  });
}

export function useDiscoverTools() {
  const invalidate = useInvalidateMcp();
  return useMutation({
    mutationFn: async (id: string) => unwrap(await api.POST("/api/v1/mcp/servers/{server_id}/discover", { params: { path: { server_id: id } } })),
    onSettled: () => void invalidate(),
  });
}

// ---- tools ----------------------------------------------------------------------------------

type ToolPatch = Schemas["MCPToolPatch"];

function applyPatch(tool: Tool, patch: ToolPatch): Tool {
  const next = { ...tool };
  if (patch.is_enabled != null && !(patch.is_enabled && tool.is_stale)) next.is_enabled = patch.is_enabled;
  if (patch.requires_approval != null) next.requires_approval = patch.requires_approval;
  if (patch.is_destructive != null) next.is_destructive = patch.is_destructive;
  if (patch.risk_level != null) next.risk_level = patch.risk_level;
  return next;
}

/** Optimistically patch tools in the cached list; returns the snapshot for rollback. */
function useOptimisticTools() {
  const qc = useQueryClient();
  return {
    async apply(ids: ReadonlySet<string>, patch: ToolPatch) {
      await qc.cancelQueries({ queryKey: mcpKeys.tools });
      const previous = qc.getQueryData<Tool[]>(mcpKeys.tools);
      qc.setQueryData<Tool[]>(mcpKeys.tools, (rows) => rows?.map((t) => (ids.has(t.id) ? applyPatch(t, patch) : t)));
      return { previous };
    },
    rollback(ctx: { previous?: Tool[] } | undefined) {
      if (ctx?.previous) qc.setQueryData(mcpKeys.tools, ctx.previous);
    },
    settle() {
      // Server tool counts change with is_enabled, so refresh the whole mcp namespace.
      void qc.invalidateQueries({ queryKey: mcpKeys.all });
    },
  };
}

export function useUpdateTool() {
  const opt = useOptimisticTools();
  return useMutation({
    mutationFn: async ({ id, patch }: { id: string; patch: ToolPatch }) =>
      unwrap(await api.PATCH("/api/v1/mcp/tools/{tool_id}", { params: { path: { tool_id: id } }, body: patch })),
    onMutate: ({ id, patch }) => opt.apply(new Set([id]), patch),
    onError: (_e, _v, ctx) => opt.rollback(ctx),
    onSettled: () => opt.settle(),
  });
}

export function useBulkUpdateTools() {
  const opt = useOptimisticTools();
  return useMutation({
    mutationFn: async ({ ids, patch }: { ids: string[]; patch: ToolPatch }) =>
      unwrap(await api.POST("/api/v1/mcp/tools/bulk", { body: { tool_ids: ids, patch } })),
    onMutate: ({ ids, patch }) => opt.apply(new Set(ids), patch),
    onError: (_e, _v, ctx) => opt.rollback(ctx),
    onSettled: () => opt.settle(),
  });
}
