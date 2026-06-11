import { CalendarRange } from "lucide-react";
import { cn } from "@/lib/utils";

export function Logo({ className }: { className?: string }) {
  return (
    <div className={cn("flex items-center gap-2.5", className)}>
      <div className="flex h-9 w-9 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lifted">
        <CalendarRange className="h-5 w-5" />
      </div>
      <div className="leading-tight">
        <span className="block text-sm font-bold tracking-tight">Kodifly</span>
        <span className="block text-[11px] text-muted-foreground">Meeting Rooms</span>
      </div>
    </div>
  );
}
