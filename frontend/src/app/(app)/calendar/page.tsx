"use client";

import { DoorOpen } from "lucide-react";
import { useState } from "react";
import { BookingCalendar } from "@/components/calendar/booking-calendar";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useRooms } from "@/hooks/use-rooms";

export default function CalendarPage() {
  const { data: rooms } = useRooms();
  const [roomFilter, setRoomFilter] = useState("all");

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Calendar</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            All bookings across rooms — click a free slot to book it.
          </p>
        </div>
        <Select value={roomFilter} onValueChange={setRoomFilter}>
          <SelectTrigger className="w-full sm:w-64" aria-label="Filter by room">
            <DoorOpen className="mr-1 h-4 w-4 text-muted-foreground" />
            <SelectValue placeholder="All rooms" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All rooms</SelectItem>
            {(rooms ?? []).map((room) => (
              <SelectItem key={room.id} value={room.id}>
                <span className="flex items-center gap-2">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: room.color }}
                  />
                  {room.name}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <BookingCalendar roomId={roomFilter === "all" ? undefined : roomFilter} />

      {rooms && rooms.length > 0 && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-muted-foreground">
          {rooms.map((room) => (
            <span key={room.id} className="inline-flex items-center gap-1.5">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: room.color }}
              />
              {room.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
