import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";

export const scheduleKeys = {
  all: ["schedules"] as const,
  list: ["schedules", "list"] as const,
  fires: (id: string) => ["schedules", "fires", id] as const,
};

export function useSchedules() {
  return useQuery({
    queryKey: scheduleKeys.list,
    queryFn: async () => unwrap(await api.GET("/api/v1/schedules")),
    refetchInterval: 30_000,
  });
}

export function useScheduleFires(id: string | undefined) {
  return useQuery({
    queryKey: scheduleKeys.fires(id ?? ""),
    queryFn: async () => unwrap(await api.GET("/api/v1/schedules/{schedule_id}/fires", { params: { path: { schedule_id: id! } } })),
    enabled: !!id,
    refetchInterval: 30_000,
  });
}

/** Pipelines a schedule can target (non-archived). */
export function usePipelineOptions() {
  return useQuery({
    queryKey: ["pipelines", "options"] as const,
    queryFn: async () => unwrap(await api.GET("/api/v1/pipelines")),
    staleTime: 60_000,
  });
}
