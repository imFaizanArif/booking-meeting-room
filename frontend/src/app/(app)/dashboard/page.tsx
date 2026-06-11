"use client";

import { CalendarCheck, CalendarClock, History, Plus, Sparkles } from "lucide-react";
import { useMemo } from "react";
import { BookingCard } from "@/components/bookings/booking-card";
import { StatCard } from "@/components/dashboard/stat-card";
import { EmptyStateIllustration } from "@/components/illustrations/meeting-illustration";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useBookings } from "@/hooks/use-bookings";
import { useMe } from "@/hooks/use-users";
import { useUiStore } from "@/stores/ui-store";
import type { Booking } from "@/lib/types";

function Section({
  title,
  icon: Icon,
  bookings,
  emptyMessage,
}: {
  title: string;
  icon: typeof CalendarCheck;
  bookings: Booking[];
  emptyMessage: string;
}) {
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <Icon className="h-4.5 w-4.5 text-primary" />
        {title}
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {bookings.length}
        </span>
      </h2>
      {bookings.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
          {emptyMessage}
        </p>
      ) : (
        <div className="space-y-3">
          {bookings.map((booking) => (
            <BookingCard key={booking.id} booking={booking} />
          ))}
        </div>
      )}
    </section>
  );
}

export default function DashboardPage() {
  const { data: me } = useMe();
  const { openBookingDialog } = useUiStore();
  const { data: bookings, isLoading } = useBookings(
    me ? { user_id: me.id } : undefined
  );

  const { today, upcoming, recent } = useMemo(() => {
    const now = new Date();
    const startOfDay = new Date(now);
    startOfDay.setHours(0, 0, 0, 0);
    const endOfDay = new Date(now);
    endOfDay.setHours(23, 59, 59, 999);

    const active = (bookings ?? []).filter(
      (b) => b.status === "confirmed" || b.status === "pending"
    );

    return {
      today: active.filter(
        (b) =>
          new Date(b.start_time) <= endOfDay && new Date(b.end_time) >= startOfDay
      ),
      upcoming: active
        .filter((b) => new Date(b.start_time) > endOfDay)
        .slice(0, 5),
      recent: (bookings ?? [])
        .filter((b) => new Date(b.end_time) < now)
        .sort(
          (a, b) =>
            new Date(b.start_time).getTime() - new Date(a.start_time).getTime()
        )
        .slice(0, 5),
    };
  }, [bookings]);

  const firstName = me?.name?.split(" ")[0] ?? "there";

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Hi {firstName} <span aria-hidden>👋</span>
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Here&apos;s what your meeting schedule looks like.
          </p>
        </div>
        <Button size="lg" onClick={() => openBookingDialog()}>
          <Plus />
          Book a room
        </Button>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label="Today's meetings"
          value={isLoading ? "…" : today.length}
          icon={Sparkles}
          tone="primary"
          delay={0}
        />
        <StatCard
          label="Upcoming"
          value={isLoading ? "…" : upcoming.length}
          icon={CalendarClock}
          tone="accent"
          delay={0.08}
        />
        <StatCard
          label="Recent meetings"
          value={isLoading ? "…" : recent.length}
          icon={History}
          tone="secondary"
          delay={0.16}
        />
      </div>

      {isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (bookings ?? []).length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-3xl border border-dashed border-border py-14 text-center">
          <EmptyStateIllustration className="h-44 w-60 text-foreground" />
          <div>
            <h2 className="font-semibold">No meetings yet</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Book your first room and it will show up here.
            </p>
          </div>
          <Button onClick={() => openBookingDialog()}>
            <Plus />
            Book your first room
          </Button>
        </div>
      ) : (
        <div className="space-y-8">
          <Section
            title="Today"
            icon={Sparkles}
            bookings={today}
            emptyMessage="No meetings today — enjoy the focus time!"
          />
          <Section
            title="Upcoming"
            icon={CalendarClock}
            bookings={upcoming}
            emptyMessage="Nothing scheduled ahead."
          />
          <Section
            title="Recent"
            icon={History}
            bookings={recent}
            emptyMessage="No past meetings yet."
          />
        </div>
      )}
    </div>
  );
}
