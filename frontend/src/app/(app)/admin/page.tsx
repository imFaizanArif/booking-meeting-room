"use client";

import { BarChart3, ClipboardList, DoorOpen, ShieldAlert, Users } from "lucide-react";
import { AnalyticsPanel } from "@/components/admin/analytics-panel";
import { BookingManager } from "@/components/admin/booking-manager";
import { RoomManager } from "@/components/admin/room-manager";
import { UserManager } from "@/components/admin/user-manager";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMe } from "@/hooks/use-users";

export default function AdminPage() {
  const { data: me, isLoading } = useMe();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-9 w-44" />
        <Skeleton className="h-96 w-full rounded-3xl" />
      </div>
    );
  }

  if (me?.role !== "admin") {
    return (
      <div className="flex flex-col items-center gap-4 rounded-3xl border border-dashed border-border py-20 text-center">
        <div className="flex h-16 w-16 items-center justify-center rounded-3xl bg-destructive/10">
          <ShieldAlert className="h-8 w-8 text-destructive" />
        </div>
        <h1 className="text-xl font-semibold">Admins only</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          You need administrator privileges to access this area. Ask an existing
          admin to grant you access.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight sm:text-3xl">Admin</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Analytics, rooms, employees and bookings — all in one place.
        </p>
      </div>

      <Tabs defaultValue="analytics">
        <TabsList className="w-full justify-start overflow-x-auto sm:w-auto">
          <TabsTrigger value="analytics">
            <BarChart3 className="h-4 w-4" />
            <span className="hidden sm:inline">Analytics</span>
          </TabsTrigger>
          <TabsTrigger value="rooms">
            <DoorOpen className="h-4 w-4" />
            <span className="hidden sm:inline">Rooms</span>
          </TabsTrigger>
          <TabsTrigger value="users">
            <Users className="h-4 w-4" />
            <span className="hidden sm:inline">Users</span>
          </TabsTrigger>
          <TabsTrigger value="bookings">
            <ClipboardList className="h-4 w-4" />
            <span className="hidden sm:inline">Bookings</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="analytics">
          <AnalyticsPanel />
        </TabsContent>
        <TabsContent value="rooms">
          <RoomManager />
        </TabsContent>
        <TabsContent value="users">
          <UserManager />
        </TabsContent>
        <TabsContent value="bookings">
          <BookingManager />
        </TabsContent>
      </Tabs>
    </div>
  );
}
