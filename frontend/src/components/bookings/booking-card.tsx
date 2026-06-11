"use client";

import { CalendarClock, DoorOpen, Pencil, Trash2, Users } from "lucide-react";
import { motion } from "framer-motion";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { useCancelBooking } from "@/hooks/use-bookings";
import { useMe } from "@/hooks/use-users";
import { useUiStore } from "@/stores/ui-store";
import type { Booking } from "@/lib/types";
import { formatDate, formatTimeRange, getInitials } from "@/lib/utils";

export function BookingCard({ booking }: { booking: Booking }) {
  const { data: me } = useMe();
  const { openBookingDialog } = useUiStore();
  const cancelBooking = useCancelBooking();

  const isOwner = me?.id === booking.user_id;
  const isAdmin = me?.role === "admin";
  const canManage = (isOwner || isAdmin) && booking.status !== "cancelled";
  const isPast = new Date(booking.end_time) < new Date();

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      layout
    >
      <Card className={isPast ? "opacity-70" : undefined}>
        <CardContent className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:p-5">
          <div
            className="hidden h-12 w-1.5 shrink-0 rounded-full sm:block"
            style={{ backgroundColor: booking.room?.color ?? "#2563EB" }}
          />
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="truncate font-semibold">{booking.title}</h3>
              <StatusBadge status={booking.status} />
            </div>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <DoorOpen className="h-3.5 w-3.5" />
                {booking.room?.name ?? "Unknown room"}
              </span>
              <span className="inline-flex items-center gap-1.5">
                <CalendarClock className="h-3.5 w-3.5" />
                {formatDate(booking.start_time)} ·{" "}
                {formatTimeRange(booking.start_time, booking.end_time)}
              </span>
              {booking.attendees.length > 0 && (
                <span className="inline-flex items-center gap-1.5">
                  <Users className="h-3.5 w-3.5" />
                  {booking.attendees.length + 1} people
                </span>
              )}
            </div>
            {booking.purpose && (
              <p className="line-clamp-1 text-sm text-muted-foreground">{booking.purpose}</p>
            )}
          </div>

          <div className="flex items-center gap-2">
            <div className="mr-2 flex -space-x-2">
              {booking.user && (
                <Avatar className="h-7 w-7 border-2 border-card">
                  <AvatarImage src={booking.user.avatar_url ?? undefined} />
                  <AvatarFallback className="text-[10px]">
                    {getInitials(booking.user.name || booking.user.email)}
                  </AvatarFallback>
                </Avatar>
              )}
              {booking.attendees.slice(0, 3).map((attendee) => (
                <Avatar key={attendee.id} className="h-7 w-7 border-2 border-card">
                  <AvatarImage src={attendee.user?.avatar_url ?? undefined} />
                  <AvatarFallback className="text-[10px]">
                    {attendee.user ? getInitials(attendee.user.name || attendee.user.email) : "?"}
                  </AvatarFallback>
                </Avatar>
              ))}
            </div>

            {canManage && !isPast && (
              <>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Edit booking"
                  onClick={() => openBookingDialog({ booking })}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label="Cancel booking"
                  className="text-destructive hover:text-destructive"
                  disabled={cancelBooking.isPending}
                  onClick={() => cancelBooking.mutate(booking.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
