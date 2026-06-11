import { Skeleton } from "@/components/ui/skeleton";

export default function CalendarLoading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-9 w-44" />
      <Skeleton className="h-[640px] w-full rounded-3xl" />
    </div>
  );
}
