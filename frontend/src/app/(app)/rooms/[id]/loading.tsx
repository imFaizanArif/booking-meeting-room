import { Skeleton } from "@/components/ui/skeleton";

export default function RoomDetailLoading() {
  return (
    <div className="space-y-6">
      <Skeleton className="h-5 w-24" />
      <Skeleton className="h-72 w-full rounded-3xl" />
      <Skeleton className="h-6 w-64" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}
