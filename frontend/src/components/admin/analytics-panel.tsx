"use client";

import { CalendarClock, ClipboardList, DoorOpen, Hourglass, Users } from "lucide-react";
import { motion } from "framer-motion";
import { StatCard } from "@/components/dashboard/stat-card";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboardStats } from "@/hooks/use-users";

export function AnalyticsPanel() {
  const { data: stats, isLoading } = useDashboardStats();

  if (isLoading || !stats) {
    return (
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  const maxDayCount = Math.max(1, ...stats.bookings_per_day.map((d) => d.count));

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total bookings"
          value={stats.total_bookings}
          icon={ClipboardList}
          tone="primary"
        />
        <StatCard
          label="Upcoming (7 days)"
          value={stats.upcoming_meetings}
          icon={CalendarClock}
          tone="accent"
          delay={0.06}
        />
        <StatCard
          label="Active rooms"
          value={stats.active_rooms}
          icon={DoorOpen}
          tone="secondary"
          delay={0.12}
        />
        <StatCard
          label="Pending approvals"
          value={stats.pending_approvals}
          icon={Hourglass}
          tone="warning"
          delay={0.18}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Room utilization */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Room utilization</CardTitle>
            <CardDescription>Booked hours over the past 7 working days.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {stats.room_utilization.length === 0 && (
              <p className="text-sm text-muted-foreground">No data yet.</p>
            )}
            {stats.room_utilization.map((room) => (
              <div key={room.room_id} className="space-y-1.5">
                <div className="flex items-center justify-between text-sm">
                  <span className="flex items-center gap-2 font-medium">
                    <span
                      className="inline-block h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: room.color }}
                    />
                    {room.room_name}
                  </span>
                  <span className="text-muted-foreground">
                    {room.booked_hours}h · {room.utilization_pct}%
                  </span>
                </div>
                <div className="h-2.5 overflow-hidden rounded-full bg-muted">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${room.utilization_pct}%` }}
                    transition={{ duration: 0.8, ease: "easeOut" }}
                    className="h-full rounded-full"
                    style={{ backgroundColor: room.color }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Bookings trend */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Bookings per day</CardTitle>
            <CardDescription>Last 7 days and the week ahead.</CardDescription>
          </CardHeader>
          <CardContent>
            {stats.bookings_per_day.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data yet.</p>
            ) : (
              <div className="flex h-48 items-end gap-2">
                {stats.bookings_per_day.map((day) => (
                  <div
                    key={day.date}
                    className="group flex flex-1 flex-col items-center gap-1.5"
                  >
                    <span className="text-xs font-medium text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
                      {day.count}
                    </span>
                    <motion.div
                      initial={{ height: 0 }}
                      animate={{
                        height: `${Math.max((day.count / maxDayCount) * 100, 4)}%`,
                      }}
                      transition={{ duration: 0.6, ease: "easeOut" }}
                      className="w-full max-w-9 rounded-t-lg bg-primary/80 transition-colors group-hover:bg-primary"
                    />
                    <span className="text-[10px] text-muted-foreground">
                      {new Date(day.date).toLocaleDateString("en", {
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <StatCard label="Active employees" value={stats.total_users} icon={Users} tone="accent" />
      </div>
    </div>
  );
}
