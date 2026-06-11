"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { roomsApi } from "@/lib/api";
import type { RoomPayload } from "@/lib/types";

export function useRooms(params?: { include_inactive?: boolean; search?: string }) {
  return useQuery({
    queryKey: ["rooms", params],
    queryFn: () => roomsApi.list(params),
  });
}

export function useRoom(id: string) {
  return useQuery({
    queryKey: ["rooms", id],
    queryFn: () => roomsApi.get(id),
    enabled: Boolean(id),
  });
}

export function useCreateRoom() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: RoomPayload) => roomsApi.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rooms"] });
      toast.success("Room created");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useUpdateRoom() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<RoomPayload> }) =>
      roomsApi.update(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rooms"] });
      toast.success("Room updated");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useDeleteRoom() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => roomsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rooms"] });
      toast.success("Room deleted");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
