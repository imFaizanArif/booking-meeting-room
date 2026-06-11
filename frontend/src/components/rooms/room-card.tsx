"use client";

import { Building2, Users } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { motion } from "framer-motion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useUiStore } from "@/stores/ui-store";
import type { Room } from "@/lib/types";

export function RoomCard({ room, index = 0 }: { room: Room; index?: number }) {
  const { openBookingDialog } = useUiStore();

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: index * 0.06, ease: "easeOut" }}
    >
      <Card className="group overflow-hidden">
        <Link href={`/rooms/${room.id}`} className="block">
          <div className="relative h-44 w-full overflow-hidden">
            {room.image_url ? (
              <Image
                src={room.image_url}
                alt={room.name}
                fill
                sizes="(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw"
                className="object-cover transition-transform duration-500 group-hover:scale-105"
              />
            ) : (
              <div
                className="h-full w-full"
                style={{
                  background: `linear-gradient(135deg, ${room.color}33, ${room.color}11)`,
                }}
              />
            )}
            <div
              className="absolute left-4 top-4 h-3 w-3 rounded-full ring-4 ring-white/60"
              style={{ backgroundColor: room.color }}
            />
            {!room.is_active && (
              <Badge variant="destructive" className="absolute right-4 top-4">
                Unavailable
              </Badge>
            )}
          </div>
        </Link>
        <CardContent className="space-y-3 p-5">
          <div className="flex items-start justify-between gap-2">
            <div>
              <Link
                href={`/rooms/${room.id}`}
                className="font-semibold leading-tight hover:text-primary"
              >
                {room.name}
              </Link>
              <div className="mt-1.5 flex items-center gap-3 text-sm text-muted-foreground">
                <span className="inline-flex items-center gap-1">
                  <Users className="h-3.5 w-3.5" />
                  {room.capacity} seats
                </span>
                <span className="inline-flex items-center gap-1">
                  <Building2 className="h-3.5 w-3.5" />
                  Floor {room.floor}
                </span>
              </div>
            </div>
          </div>
          <p className="line-clamp-2 min-h-10 text-sm text-muted-foreground">
            {room.description}
          </p>
          <Button
            className="w-full"
            disabled={!room.is_active}
            onClick={() => openBookingDialog({ defaults: { roomId: room.id } })}
          >
            Book this room
          </Button>
        </CardContent>
      </Card>
    </motion.div>
  );
}
