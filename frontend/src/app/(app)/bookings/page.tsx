"use client";

import { CalendarRange, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { BookingCard } from "@/components/bookings/booking-card";
import { EmptyStateIllustration } from "@/components/illustrations/meeting-illustration";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useBookings } from "@/hooks/use-bookings";
import { useRooms } from "@/hooks/use-rooms";
import { useMe } from "@/hooks/use-users";
import { useUiStore } from "@/stores/ui-store";

type TimeFilter = "all" | "today" | "week";

export default function BookingsPage() {
  const { data: me } = useMe();
  const { data: rooms } = useRooms();
  const { openBookingDialog } = useUiStore();

  const [search, setSearch] = useState("");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("all");
  const [roomFilter, setRoomFilter] = useState("all");

  const { data: bookings, isLoading } = useBookings(
    me ? { user_id: me.id } : undefined
  );

  const filtered = useMemo(() => {
    const now = new Date();
    const startOfDay = new Date(now);
    startOfDay.setHours(0, 0, 0, 0);
    const endOfDay = new Date(now);
    endOfDay.setHours(23, 59, 59, 999);
    const endOfWeek = new Date(startOfDay);
    endOfWeek.setDate(endOfWeek.getDate() + 7);

    return (bookings ?? [])
      .filter((b) => {
        if (roomFilter !== "all" && b.room_id !== roomFilter) return false;

        const start = new Date(b.start_time);
        if (timeFilter === "today" && (start < startOfDay || start > endOfDay))
          return false;
        if (timeFilter === "week" && (start < startOfDay || start > endOfWeek))
          return false;

        if (search) {
          const q = search.toLowerCase();
          const inTitle = b.title.toLowerCase().includes(q);
          const inRoom = b.room?.name.toLowerCase().includes(q) ?? false;
          const inPeople =
            (b.user?.name.toLowerCase().includes(q) ?? false) ||
            b.attendees.some((a) => a.user?.name.toLowerCase().includes(q));
          if (!inTitle && !inRoom && !inPeople) return false;
        }
        return true;
      })
      .sort(
        (a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime()
      );
  }, [bookings, search, timeFilter, roomFilter]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">My Bookings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Meetings you organised or were invited to.
          </p>
        </div>
        <Button onClick={() => openBookingDialog()}>
          <Plus />
          New booking
        </Button>
      </div>

      {/* Search + filters */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by meeting title, room or employee…"
            className="pl-9"
            aria-label="Search bookings"
          />
        </div>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Tabs value={timeFilter} onValueChange={(v) => setTimeFilter(v as TimeFilter)}>
            <TabsList>
              <TabsTrigger value="all">All</TabsTrigger>
              <TabsTrigger value="today">Today</TabsTrigger>
              <TabsTrigger value="week">This week</TabsTrigger>
            </TabsList>
          </Tabs>
          <Select value={roomFilter} onValueChange={setRoomFilter}>
            <SelectTrigger className="w-full sm:w-56" aria-label="Filter by room">
              <CalendarRange className="mr-1 h-4 w-4 text-muted-foreground" />
              <SelectValue placeholder="All rooms" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All rooms</SelectItem>
              {(rooms ?? []).map((room) => (
                <SelectItem key={room.id} value={room.id}>
                  {room.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-3xl border border-dashed border-border py-14 text-center">
          <EmptyStateIllustration className="h-40 w-56 text-foreground" />
          <p className="text-sm text-muted-foreground">
            No bookings match your filters.
          </p>
          <Button variant="outline" onClick={() => openBookingDialog()}>
            <Plus className="h-4 w-4" />
            Book a room
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((booking) => (
            <BookingCard key={booking.id} booking={booking} />
          ))}
        </div>
      )}
    </div>
  );
}
