import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type Schemas } from "@/lib/api/client";

type ApprovalStatus = Schemas["ApprovalStatus"];

export const approvalKeys = {
  all: ["approvals"] as const,
  list: (status: ApprovalStatus | "all", offset: number) => ["approvals", "list", status, offset] as const,
  detail: (id: string) => ["approvals", "detail", id] as const,
};

export function useApprovals(status: ApprovalStatus | "all", offset = 0, limit = 50) {
  return useQuery({
    queryKey: approvalKeys.list(status, offset),
    queryFn: async () =>
      unwrap(await api.GET("/api/v1/approvals", { params: { query: { status: status === "all" ? undefined : status, offset, limit } } })),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  });
}

export function usePendingCount() {
  return useQuery({
    queryKey: [...approvalKeys.all, "pending-count"],
    queryFn: async () => unwrap(await api.GET("/api/v1/approvals", { params: { query: { status: "pending", limit: 1 } } })).total,
    refetchInterval: 20_000,
  });
}

export function useApproval(id: string | undefined) {
  return useQuery({
    queryKey: approvalKeys.detail(id ?? ""),
    queryFn: async () => unwrap(await api.GET("/api/v1/approvals/{approval_id}", { params: { path: { approval_id: id! } } })),
    enabled: !!id,
  });
}

export function useDecide(id: string) {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: Schemas["DecisionIn"]) =>
      unwrap(await api.POST("/api/v1/approvals/{approval_id}/decision", { params: { path: { approval_id: id } }, body })),
    onSuccess: (data) => {
      qc.setQueryData(approvalKeys.detail(id), data);
      void qc.invalidateQueries({ queryKey: approvalKeys.all });
      void qc.invalidateQueries({ queryKey: ["executions"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}
