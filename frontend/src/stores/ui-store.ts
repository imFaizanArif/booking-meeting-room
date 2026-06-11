"use client";

import { create } from "zustand";
import type { Booking } from "@/lib/types";

interface UiState {
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;

  bookingDialogOpen: boolean;
  editingBooking: Booking | null;
  bookingDefaults: { roomId?: string; start?: string; end?: string } | null;
  openBookingDialog: (opts?: {
    booking?: Booking;
    defaults?: { roomId?: string; start?: string; end?: string };
  }) => void;
  closeBookingDialog: () => void;
}

export const useUiStore = create<UiState>((set) => ({
  sidebarOpen: false,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  bookingDialogOpen: false,
  editingBooking: null,
  bookingDefaults: null,
  openBookingDialog: (opts) =>
    set({
      bookingDialogOpen: true,
      editingBooking: opts?.booking ?? null,
      bookingDefaults: opts?.defaults ?? null,
    }),
  closeBookingDialog: () =>
    set({ bookingDialogOpen: false, editingBooking: null, bookingDefaults: null }),
}));
