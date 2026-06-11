"use client";

import { Ban, Check, Search, X } from "lucide-react";
import { useState } from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { useBookings, useCancelBooking, useUpdateBooking } from "@/hooks/use-bookings";
import { formatDate, formatTimeRange, getInitials } from "@/lib/utils";

export function BookingManager() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");

  const { data: bookings, isLoading } = useBookings({
    search: search || undefined,
    status: statusFilter === "all" ? undefined : statusFilter,
  });
  const updateBooking = useUpdateBooking();
  const cancelBooking = useCancelBooking();

  const sorted = [...(bookings ?? [])].sort(
    (a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime()
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by meeting title…"
            className="pl-9"
            aria-label="Search bookings"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter}>
          <SelectTrigger className="w-full sm:w-48" aria-label="Filter by status">
            <SelectValue placeholder="All statuses" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="confirmed">Confirmed</SelectItem>
            <SelectItem value="rejected">Rejected</SelectItem>
            <SelectItem value="cancelled">Cancelled</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : sorted.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
          No bookings found.
        </p>
      ) : (
        <div className="space-y-3">
          {sorted.map((booking) => {
            const isActionable =
              booking.status === "pending" || booking.status === "confirmed";
            return (
              <Card key={booking.id}>
                <CardContent className="flex flex-col gap-3 p-4 lg:flex-row lg:items-center">
                  <span
                    className="hidden h-12 w-1.5 shrink-0 rounded-full lg:block"
                    style={{ backgroundColor: booking.room?.color ?? "#2563EB" }}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{booking.title}</span>
                      <StatusBadge status={booking.status} />
                    </div>
                    <p className="mt-0.5 text-sm text-muted-foreground">
                      {booking.room?.name} · {formatDate(booking.start_time)} ·{" "}
                      {formatTimeRange(booking.start_time, booking.end_time)}
                    </p>
                    <div className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground">
                      <Avatar className="h-5 w-5">
                        <AvatarImage src={booking.user?.avatar_url ?? undefined} />
                        <AvatarFallback className="text-[8px]">
                          {booking.user
                            ? getInitials(booking.user.name || booking.user.email)
                            : "?"}
                        </AvatarFallback>
                      </Avatar>
                      Booked by {booking.user?.name ?? "Unknown"}
                    </div>
                  </div>
                  {isActionable && (
                    <div className="flex shrink-0 flex-wrap items-center gap-2">
                      {booking.status === "pending" && (
                        <Button
                          size="sm"
                          variant="accent"
                          disabled={updateBooking.isPending}
                          onClick={() =>
                            updateBooking.mutate({
                              id: booking.id,
                              payload: { status: "confirmed" },
                            })
                          }
                        >
                          <Check className="h-4 w-4" />
                          Approve
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={updateBooking.isPending}
                        onClick={() =>
                          updateBooking.mutate({
                            id: booking.id,
                            payload: { status: "rejected" },
                          })
                        }
                      >
                        <X className="h-4 w-4" />
                        Reject
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive"
                        disabled={cancelBooking.isPending}
                        onClick={() => cancelBooking.mutate(booking.id)}
                      >
                        <Ban className="h-4 w-4" />
                        Cancel
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
