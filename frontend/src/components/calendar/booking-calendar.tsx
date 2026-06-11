"use client";

import FullCalendar from "@fullcalendar/react";
import dayGridPlugin from "@fullcalendar/daygrid";
import timeGridPlugin from "@fullcalendar/timegrid";
import interactionPlugin from "@fullcalendar/interaction";
import type { DateSelectArg, EventClickArg } from "@fullcalendar/core";
import { useMemo } from "react";
import { useBookings } from "@/hooks/use-bookings";
import { useMe } from "@/hooks/use-users";
import { useUiStore } from "@/stores/ui-store";
import type { Booking } from "@/lib/types";

export function BookingCalendar({ roomId }: { roomId?: string }) {
  const { data: bookings } = useBookings(roomId ? { room_id: roomId } : undefined);
  const { data: me } = useMe();
  const { openBookingDialog } = useUiStore();

  const events = useMemo(
    () =>
      (bookings ?? [])
        .filter((b) => b.status === "confirmed" || b.status === "pending")
        .map((booking) => ({
          id: booking.id,
          title: `${booking.title} · ${booking.room?.name ?? ""}`,
          start: booking.start_time,
          end: booking.end_time,
          backgroundColor: booking.room?.color ?? "#2563EB",
          borderColor: "transparent",
          textColor: "#ffffff",
          extendedProps: { booking },
        })),
    [bookings]
  );

  function handleEventClick(info: EventClickArg) {
    const booking = info.event.extendedProps.booking as Booking;
    const canEdit =
      me && (me.id === booking.user_id || me.role === "admin") &&
      booking.status !== "cancelled" &&
      new Date(booking.end_time) > new Date();
    if (canEdit) {
      openBookingDialog({ booking });
    }
  }

  function handleSelect(info: DateSelectArg) {
    openBookingDialog({
      defaults: {
        roomId,
        start: info.start.toISOString(),
        end: info.end.toISOString(),
      },
    });
  }

  return (
    <div className="rounded-3xl border border-border/60 bg-card p-4 shadow-soft sm:p-6">
      <FullCalendar
        plugins={[dayGridPlugin, timeGridPlugin, interactionPlugin]}
        initialView="dayGridMonth"
        headerToolbar={{
          left: "prev,next today",
          center: "title",
          right: "dayGridMonth,timeGridWeek,timeGridDay",
        }}
        events={events}
        selectable
        selectMirror
        select={handleSelect}
        eventClick={handleEventClick}
        height="auto"
        nowIndicator
        dayMaxEventRows={4}
        slotMinTime="07:00:00"
        slotMaxTime="21:00:00"
        scrollTime="08:30:00"
        firstDay={1}
        expandRows
        stickyHeaderDates
        eventTimeFormat={{ hour: "numeric", minute: "2-digit", meridiem: "short" }}
      />
    </div>
  );
}
