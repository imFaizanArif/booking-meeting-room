"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { analyticsApi, usersApi } from "@/lib/api";
import type { Profile } from "@/lib/types";

export function useUsers(search?: string) {
  return useQuery({
    queryKey: ["users", search],
    queryFn: () => usersApi.list(search),
  });
}

export function useMe() {
  return useQuery({
    queryKey: ["users", "me"],
    queryFn: () => usersApi.me(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useUpdateMe() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<Profile>) => usersApi.updateMe(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      toast.success("Profile updated");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useAdminUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<Profile> }) =>
      usersApi.adminUpdate(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      toast.success("User updated");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useDashboardStats() {
  return useQuery({
    queryKey: ["analytics", "dashboard"],
    queryFn: () => analyticsApi.dashboard(),
    refetchInterval: 60_000,
  });
}
