"use client";

import { Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCreateRoom,
  useDeleteRoom,
  useRooms,
  useUpdateRoom,
} from "@/hooks/use-rooms";
import type { Room, RoomPayload } from "@/lib/types";

const EMPTY_FORM: RoomPayload = {
  name: "",
  capacity: 4,
  floor: 1,
  description: "",
  image_url: "",
  color: "#2563EB",
  is_active: true,
};

export function RoomManager() {
  const { data: rooms, isLoading } = useRooms({ include_inactive: true });
  const createRoom = useCreateRoom();
  const updateRoom = useUpdateRoom();
  const deleteRoom = useDeleteRoom();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<Room | null>(null);
  const [form, setForm] = useState<RoomPayload>(EMPTY_FORM);
  const [deleteTarget, setDeleteTarget] = useState<Room | null>(null);

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDialogOpen(true);
  }

  function openEdit(room: Room) {
    setEditing(room);
    setForm({
      name: room.name,
      capacity: room.capacity,
      floor: room.floor,
      description: room.description,
      image_url: room.image_url ?? "",
      color: room.color,
      is_active: room.is_active,
    });
    setDialogOpen(true);
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const payload = { ...form, image_url: form.image_url || null };
    if (editing) {
      await updateRoom.mutateAsync({ id: editing.id, payload });
    } else {
      await createRoom.mutateAsync(payload);
    }
    setDialogOpen(false);
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    await deleteRoom.mutateAsync(deleteTarget.id);
    setDeleteTarget(null);
  }

  const pending = createRoom.isPending || updateRoom.isPending;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          {rooms?.length ?? 0} rooms configured
        </p>
        <Button onClick={openCreate}>
          <Plus />
          Add room
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full" />
          ))}
        </div>
      ) : (
        <div className="space-y-3">
          {(rooms ?? []).map((room) => (
            <Card key={room.id}>
              <CardContent className="flex items-center gap-4 p-4">
                <span
                  className="h-10 w-1.5 shrink-0 rounded-full"
                  style={{ backgroundColor: room.color }}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{room.name}</span>
                    {!room.is_active && <Badge variant="destructive">Inactive</Badge>}
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {room.capacity} seats · Floor {room.floor}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Edit ${room.name}`}
                  onClick={() => openEdit(room)}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  aria-label={`Delete ${room.name}`}
                  className="text-destructive hover:text-destructive"
                  onClick={() => setDeleteTarget(room)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Create / edit dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editing ? `Edit ${editing.name}` : "Add a room"}</DialogTitle>
            <DialogDescription>
              {editing
                ? "Update this room's details."
                : "Create a new bookable meeting space."}
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="room-name">Name</Label>
              <Input
                id="room-name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Meeting Room Gamma"
                required
                minLength={2}
              />
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="room-capacity">Capacity</Label>
                <Input
                  id="room-capacity"
                  type="number"
                  min={1}
                  max={500}
                  value={form.capacity}
                  onChange={(e) => setForm({ ...form, capacity: Number(e.target.value) })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="room-floor">Floor</Label>
                <Input
                  id="room-floor"
                  type="number"
                  min={-5}
                  max={200}
                  value={form.floor}
                  onChange={(e) => setForm({ ...form, floor: Number(e.target.value) })}
                  required
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="room-color">Color</Label>
                <Input
                  id="room-color"
                  type="color"
                  value={form.color}
                  onChange={(e) => setForm({ ...form, color: e.target.value })}
                  className="h-10 cursor-pointer p-1.5"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="room-image">Image URL</Label>
              <Input
                id="room-image"
                type="url"
                value={form.image_url ?? ""}
                onChange={(e) => setForm({ ...form, image_url: e.target.value })}
                placeholder="https://images.unsplash.com/…"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="room-description">Description</Label>
              <Textarea
                id="room-description"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                rows={2}
              />
            </div>
            <div className="flex items-center justify-between rounded-2xl border border-border/60 px-4 py-3">
              <div>
                <p className="text-sm font-medium">Active</p>
                <p className="text-xs text-muted-foreground">
                  Inactive rooms can&apos;t be booked.
                </p>
              </div>
              <Switch
                checked={form.is_active}
                onCheckedChange={(checked) => setForm({ ...form, is_active: checked })}
                aria-label="Room active"
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={pending}>
                {pending && <Loader2 className="animate-spin" />}
                {editing ? "Save changes" : "Create room"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation */}
      <Dialog open={Boolean(deleteTarget)} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Delete {deleteTarget?.name}?</DialogTitle>
            <DialogDescription>
              This permanently removes the room and all its bookings. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              Keep room
            </Button>
            <Button
              variant="destructive"
              disabled={deleteRoom.isPending}
              onClick={handleDelete}
            >
              {deleteRoom.isPending && <Loader2 className="animate-spin" />}
              Delete room
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
