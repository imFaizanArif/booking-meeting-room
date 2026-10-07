import { useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: async () => unwrap(await api.GET("/api/v1/dashboard")),
    refetchInterval: 15_000,
  });
}
