"use client";

import { Search } from "lucide-react";
import { useState } from "react";
import { RoomCard } from "@/components/rooms/room-card";
import { EmptyStateIllustration } from "@/components/illustrations/meeting-illustration";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useRooms } from "@/hooks/use-rooms";

export default function RoomsPage() {
  const [search, setSearch] = useState("");
  const { data: rooms, isLoading } = useRooms();

  const filtered = (rooms ?? []).filter((room) =>
    room.name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Rooms</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Browse all meeting spaces at Kodifly HQ.
          </p>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search rooms…"
            className="pl-9"
            aria-label="Search rooms"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-80" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center gap-4 rounded-3xl border border-dashed border-border py-14 text-center">
          <EmptyStateIllustration className="h-40 w-56 text-foreground" />
          <p className="text-sm text-muted-foreground">
            No rooms match &quot;{search}&quot;.
          </p>
        </div>
      ) : (
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((room, index) => (
            <RoomCard key={room.id} room={room} index={index} />
          ))}
        </div>
      )}
    </div>
  );
}
