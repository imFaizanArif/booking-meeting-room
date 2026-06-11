import { Skeleton } from "@/components/ui/skeleton";

export default function ProfileLoading() {
  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <Skeleton className="h-9 w-44" />
      <Skeleton className="h-96 w-full rounded-3xl" />
    </div>
  );
}
