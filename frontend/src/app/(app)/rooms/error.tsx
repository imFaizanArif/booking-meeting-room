"use client";

import { RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function RoomsError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-4 rounded-3xl border border-dashed border-border py-16 text-center">
      <h2 className="text-lg font-semibold">Couldn&apos;t load rooms</h2>
      <p className="max-w-sm text-sm text-muted-foreground">{error.message}</p>
      <Button onClick={reset}>
        <RotateCcw className="h-4 w-4" />
        Retry
      </Button>
    </div>
  );
}
