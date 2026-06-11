import { Skeleton } from "@/components/ui/skeleton";

export default function RoomsLoading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-9 w-44" />
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-80" />
        ))}
      </div>
    </div>
  );
}
