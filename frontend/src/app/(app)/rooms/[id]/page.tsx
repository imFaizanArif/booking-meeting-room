"use client";

import { ArrowLeft, Building2, CalendarPlus, Users } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { use, useMemo } from "react";
import { motion } from "framer-motion";
import { BookingCard } from "@/components/bookings/booking-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useBookings } from "@/hooks/use-bookings";
import { useRoom } from "@/hooks/use-rooms";
import { useUiStore } from "@/stores/ui-store";

export default function RoomDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const { data: room, isLoading } = useRoom(id);
  const { openBookingDialog } = useUiStore();

  const startOfToday = useMemo(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.toISOString();
  }, []);

  const { data: bookings, isLoading: bookingsLoading } = useBookings({
    room_id: id,
    start_after: startOfToday,
  });

  const upcoming = (bookings ?? []).filter(
    (b) => b.status === "confirmed" || b.status === "pending"
  );

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-64 w-full rounded-3xl" />
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (!room) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <h1 className="text-xl font-semibold">Room not found</h1>
        <Button asChild variant="outline">
          <Link href="/rooms">
            <ArrowLeft className="h-4 w-4" />
            Back to rooms
          </Link>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <Link
        href="/rooms"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        All rooms
      </Link>

      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="overflow-hidden rounded-3xl border border-border/60 shadow-glass"
      >
        <div className="relative h-56 w-full sm:h-72">
          {room.image_url ? (
            <Image
              src={room.image_url}
              alt={room.name}
              fill
              priority
              sizes="(max-width: 1024px) 100vw, 1024px"
              className="object-cover"
            />
          ) : (
            <div
              className="h-full w-full"
              style={{
                background: `linear-gradient(135deg, ${room.color}44, ${room.color}11)`,
              }}
            />
          )}
          <div className="absolute inset-0 bg-gradient-to-t from-secondary/80 via-secondary/20 to-transparent" />
          <div className="absolute bottom-0 left-0 right-0 p-6 text-white sm:p-8">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">{room.name}</h1>
              {!room.is_active && <Badge variant="destructive">Unavailable</Badge>}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-4 text-sm text-white/85">
              <span className="inline-flex items-center gap-1.5">
                <Users className="h-4 w-4" />
                {room.capacity} seats
              </span>
              <span className="inline-flex items-center gap-1.5">
                <Building2 className="h-4 w-4" />
                Floor {room.floor}
              </span>
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-4 bg-card p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
          <p className="max-w-2xl text-sm text-muted-foreground">{room.description}</p>
          <Button
            size="lg"
            className="shrink-0"
            disabled={!room.is_active}
            onClick={() => openBookingDialog({ defaults: { roomId: room.id } })}
          >
            <CalendarPlus />
            Book this room
          </Button>
        </div>
      </motion.div>

      <section className="space-y-3">
        <h2 className="text-base font-semibold">Upcoming bookings in this room</h2>
        {bookingsLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : upcoming.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
            No upcoming bookings — the room is all yours.
          </p>
        ) : (
          <div className="space-y-3">
            {upcoming.map((booking) => (
              <BookingCard key={booking.id} booking={booking} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
