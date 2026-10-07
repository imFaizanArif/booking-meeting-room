import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/lib/api/client";

export const authKeys = { me: ["auth", "me"] as const };

export function useMe() {
  return useQuery({ queryKey: authKeys.me, queryFn: async () => unwrap(await api.GET("/api/v1/auth/me")), staleTime: 60_000 });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    meta: { silent: true },
    mutationFn: async (body: { email: string; password: string }) => unwrap(await api.POST("/api/v1/auth/login", { body })),
    onSuccess: (me) => qc.setQueryData(authKeys.me, me),
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/auth/logout")),
    onSettled: () => {
      qc.clear();
      window.location.href = "/login";
    },
  });
}

export function canOperate(role: string | undefined): boolean {
  return role === "owner" || role === "operator";
}
