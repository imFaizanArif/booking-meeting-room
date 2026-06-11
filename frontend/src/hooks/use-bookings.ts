"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { bookingsApi, type BookingFilters } from "@/lib/api";
import type { BookingPayload } from "@/lib/types";

export function useBookings(filters?: BookingFilters) {
  return useQuery({
    queryKey: ["bookings", filters],
    queryFn: () => bookingsApi.list(filters),
  });
}

export function useCreateBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: BookingPayload) => bookingsApi.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
      toast.success("Room booked successfully");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useUpdateBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: Partial<BookingPayload> & { status?: string };
    }) => bookingsApi.update(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
      toast.success("Booking updated");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useCancelBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => bookingsApi.cancel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
      toast.success("Booking cancelled");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useDeleteBooking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => bookingsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bookings"] });
      queryClient.invalidateQueries({ queryKey: ["analytics"] });
      toast.success("Booking deleted");
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
