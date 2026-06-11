"use client";

import { createClient } from "@/lib/supabase/client";
import type {
  Booking,
  BookingPayload,
  DashboardStats,
  Profile,
  Room,
  RoomPayload,
} from "@/lib/types";

// Defaults to the same-origin /api proxy (see next.config.ts rewrites), which
// works in dev (proxied to localhost:5000) and on Vercel without CORS.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code: string
  ) {
    super(message);
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(session?.access_token
        ? { Authorization: `Bearer ${session.access_token}` }
        : {}),
      ...options.headers,
    },
  });

  const body = await res.json().catch(() => null);

  if (!res.ok) {
    const message = body?.error?.message ?? `Request failed (${res.status})`;
    throw new ApiError(message, res.status, body?.error?.code ?? "unknown");
  }

  return body.data as T;
}

// ---------------------------------------------------------------------------
// Rooms
// ---------------------------------------------------------------------------
export const roomsApi = {
  list: (params?: { include_inactive?: boolean; search?: string }) => {
    const query = new URLSearchParams();
    if (params?.include_inactive) query.set("include_inactive", "true");
    if (params?.search) query.set("search", params.search);
    const qs = query.toString();
    return request<Room[]>(`/rooms${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => request<Room>(`/rooms/${id}`),
  create: (payload: RoomPayload) =>
    request<Room>("/rooms", { method: "POST", body: JSON.stringify(payload) }),
  update: (id: string, payload: Partial<RoomPayload>) =>
    request<Room>(`/rooms/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  remove: (id: string) => request<{ deleted: boolean }>(`/rooms/${id}`, { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// Bookings
// ---------------------------------------------------------------------------
export interface BookingFilters {
  room_id?: string;
  user_id?: string;
  status?: string;
  start_after?: string;
  end_before?: string;
  search?: string;
}

export const bookingsApi = {
  list: (filters?: BookingFilters) => {
    const query = new URLSearchParams();
    Object.entries(filters ?? {}).forEach(([key, value]) => {
      if (value) query.set(key, value);
    });
    const qs = query.toString();
    return request<Booking[]>(`/bookings${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => request<Booking>(`/bookings/${id}`),
  availability: (room_id: string, start_time: string, end_time: string) =>
    request<{ available: boolean; conflicts: Booking[] }>(
      `/bookings/availability?room_id=${room_id}&start_time=${encodeURIComponent(
        start_time
      )}&end_time=${encodeURIComponent(end_time)}`
    ),
  create: (payload: BookingPayload) =>
    request<Booking>("/bookings", { method: "POST", body: JSON.stringify(payload) }),
  update: (id: string, payload: Partial<BookingPayload> & { status?: string }) =>
    request<Booking>(`/bookings/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
  cancel: (id: string) => request<Booking>(`/bookings/${id}/cancel`, { method: "POST" }),
  remove: (id: string) =>
    request<{ deleted: boolean }>(`/bookings/${id}`, { method: "DELETE" }),
};

// ---------------------------------------------------------------------------
// Users
// ---------------------------------------------------------------------------
export const usersApi = {
  list: (search?: string) =>
    request<Profile[]>(`/users${search ? `?search=${encodeURIComponent(search)}` : ""}`),
  me: () => request<Profile>("/users/me"),
  updateMe: (payload: Partial<Profile>) =>
    request<Profile>("/users/me", { method: "PUT", body: JSON.stringify(payload) }),
  adminUpdate: (id: string, payload: Partial<Profile>) =>
    request<Profile>(`/users/${id}`, { method: "PUT", body: JSON.stringify(payload) }),
};

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------
export const analyticsApi = {
  dashboard: () => request<DashboardStats>("/analytics/dashboard"),
};
