"use client";

import { CalendarPlus, Check, Loader2, TriangleAlert, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useCreateBooking, useUpdateBooking } from "@/hooks/use-bookings";
import { useRooms } from "@/hooks/use-rooms";
import { useMe, useUsers } from "@/hooks/use-users";
import { bookingsApi } from "@/lib/api";
import { useUiStore } from "@/stores/ui-store";
import { cn, getInitials } from "@/lib/utils";

function toLocalInputValue(iso: string): string {
  const date = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}`;
}

function defaultStart(): string {
  const date = new Date();
  date.setMinutes(0, 0, 0);
  date.setHours(date.getHours() + 1);
  return toLocalInputValue(date.toISOString());
}

function defaultEnd(): string {
  const date = new Date();
  date.setMinutes(0, 0, 0);
  date.setHours(date.getHours() + 2);
  return toLocalInputValue(date.toISOString());
}

export function BookingDialog() {
  const {
    bookingDialogOpen,
    editingBooking,
    bookingDefaults,
    closeBookingDialog,
  } = useUiStore();

  const { data: rooms } = useRooms();
  const { data: users } = useUsers();
  const { data: me } = useMe();
  const createBooking = useCreateBooking();
  const updateBooking = useUpdateBooking();

  const [roomId, setRoomId] = useState("");
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [start, setStart] = useState(defaultStart());
  const [end, setEnd] = useState(defaultEnd());
  const [attendeeIds, setAttendeeIds] = useState<string[]>([]);
  const [attendeeSearch, setAttendeeSearch] = useState("");

  // Re-initialise the form each time the dialog opens.
  useEffect(() => {
    if (!bookingDialogOpen) return;
    if (editingBooking) {
      setRoomId(editingBooking.room_id);
      setTitle(editingBooking.title);
      setPurpose(editingBooking.purpose);
      setStart(toLocalInputValue(editingBooking.start_time));
      setEnd(toLocalInputValue(editingBooking.end_time));
      setAttendeeIds(editingBooking.attendees.map((a) => a.user_id));
    } else {
      setRoomId(bookingDefaults?.roomId ?? "");
      setTitle("");
      setPurpose("");
      setStart(bookingDefaults?.start ? toLocalInputValue(bookingDefaults.start) : defaultStart());
      setEnd(bookingDefaults?.end ? toLocalInputValue(bookingDefaults.end) : defaultEnd());
      setAttendeeIds([]);
    }
    setAttendeeSearch("");
  }, [bookingDialogOpen, editingBooking, bookingDefaults]);

  const startIso = useMemo(
    () => (start ? new Date(start).toISOString() : ""),
    [start]
  );
  const endIso = useMemo(() => (end ? new Date(end).toISOString() : ""), [end]);
  const timesValid = startIso && endIso && new Date(endIso) > new Date(startIso);

  // Live conflict detection.
  const { data: availability, isFetching: checkingAvailability } = useQuery({
    queryKey: ["availability", roomId, startIso, endIso, editingBooking?.id],
    queryFn: () => bookingsApi.availability(roomId, startIso, endIso),
    enabled: Boolean(bookingDialogOpen && roomId && timesValid),
    staleTime: 10_000,
  });

  const conflicts = (availability?.conflicts ?? []).filter(
    (c) => c.id !== editingBooking?.id
  );
  const hasConflict = conflicts.length > 0;

  const filteredUsers = (users ?? []).filter(
    (u) =>
      u.id !== me?.id &&
      u.is_active &&
      (u.name.toLowerCase().includes(attendeeSearch.toLowerCase()) ||
        u.email.toLowerCase().includes(attendeeSearch.toLowerCase()))
  );

  const pending = createBooking.isPending || updateBooking.isPending;
  const canSubmit = roomId && title.trim().length >= 3 && timesValid && !hasConflict && !pending;

  function toggleAttendee(id: string) {
    setAttendeeIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;

    const payload = {
      room_id: roomId,
      title: title.trim(),
      purpose: purpose.trim(),
      start_time: startIso,
      end_time: endIso,
      attendee_ids: attendeeIds,
    };

    if (editingBooking) {
      await updateBooking.mutateAsync({ id: editingBooking.id, payload });
    } else {
      await createBooking.mutateAsync(payload);
    }
    closeBookingDialog();
  }

  return (
    <Dialog open={bookingDialogOpen} onOpenChange={(open) => !open && closeBookingDialog()}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarPlus className="h-5 w-5 text-primary" />
            {editingBooking ? "Edit booking" : "Book a room"}
          </DialogTitle>
          <DialogDescription>
            {editingBooking
              ? "Update the details of your meeting."
              : "Pick a room, choose a time and invite your team."}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label>Room</Label>
            <Select value={roomId} onValueChange={setRoomId}>
              <SelectTrigger>
                <SelectValue placeholder="Select a room" />
              </SelectTrigger>
              <SelectContent>
                {(rooms ?? []).map((room) => (
                  <SelectItem key={room.id} value={room.id}>
                    <span className="flex items-center gap-2">
                      <span
                        className="inline-block h-2.5 w-2.5 rounded-full"
                        style={{ backgroundColor: room.color }}
                      />
                      {room.name} · {room.capacity} seats · Floor {room.floor}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="booking-title">Meeting title</Label>
            <Input
              id="booking-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Weekly product sync"
              minLength={3}
              maxLength={120}
              required
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="booking-start">Starts</Label>
              <Input
                id="booking-start"
                type="datetime-local"
                value={start}
                onChange={(e) => setStart(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="booking-end">Ends</Label>
              <Input
                id="booking-end"
                type="datetime-local"
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                required
              />
            </div>
          </div>

          {!timesValid && start && end && (
            <p className="text-sm text-destructive">End time must be after the start time.</p>
          )}

          {roomId && timesValid && (
            <div
              className={cn(
                "flex items-start gap-2 rounded-2xl px-3 py-2.5 text-sm",
                hasConflict
                  ? "bg-destructive/10 text-destructive"
                  : "bg-accent/10 text-accent"
              )}
            >
              {checkingAvailability ? (
                <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin" />
              ) : hasConflict ? (
                <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              ) : (
                <Check className="mt-0.5 h-4 w-4 shrink-0" />
              )}
              <span>
                {checkingAvailability
                  ? "Checking availability…"
                  : hasConflict
                    ? `Conflicts with "${conflicts[0].title}". Choose a different time or room.`
                    : "This slot is available."}
              </span>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="booking-purpose">Purpose</Label>
            <Textarea
              id="booking-purpose"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
              placeholder="What is this meeting about?"
              rows={2}
              maxLength={2000}
            />
          </div>

          <div className="space-y-2">
            <Label>Invite attendees</Label>
            {attendeeIds.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {attendeeIds.map((id) => {
                  const user = users?.find((u) => u.id === id);
                  if (!user) return null;
                  return (
                    <Badge key={id} variant="default" className="gap-1 pr-1">
                      {user.name || user.email}
                      <button
                        type="button"
                        aria-label={`Remove ${user.name}`}
                        onClick={() => toggleAttendee(id)}
                        className="rounded-full p-0.5 hover:bg-primary/20"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </Badge>
                  );
                })}
              </div>
            )}
            <Input
              value={attendeeSearch}
              onChange={(e) => setAttendeeSearch(e.target.value)}
              placeholder="Search colleagues by name or email…"
            />
            {attendeeSearch && (
              <div className="max-h-40 space-y-1 overflow-y-auto rounded-2xl border border-border/60 p-1.5">
                {filteredUsers.length === 0 && (
                  <p className="px-2 py-1.5 text-sm text-muted-foreground">No matches.</p>
                )}
                {filteredUsers.slice(0, 8).map((user) => (
                  <button
                    key={user.id}
                    type="button"
                    onClick={() => toggleAttendee(user.id)}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-xl px-2 py-1.5 text-left text-sm transition-colors hover:bg-muted",
                      attendeeIds.includes(user.id) && "bg-primary/5"
                    )}
                  >
                    <Avatar className="h-7 w-7">
                      <AvatarImage src={user.avatar_url ?? undefined} alt={user.name} />
                      <AvatarFallback className="text-[10px]">
                        {getInitials(user.name || user.email)}
                      </AvatarFallback>
                    </Avatar>
                    <span className="flex-1 truncate">
                      <span className="block truncate font-medium">{user.name}</span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {user.email}
                      </span>
                    </span>
                    {attendeeIds.includes(user.id) && (
                      <Check className="h-4 w-4 shrink-0 text-primary" />
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={closeBookingDialog}>
              Cancel
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {pending && <Loader2 className="animate-spin" />}
              {editingBooking ? "Save changes" : "Book room"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
