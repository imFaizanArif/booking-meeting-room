import { AlertTriangle, type LucideIcon } from "lucide-react";
import * as React from "react";

import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { Button } from "./button";

export function EmptyState({ icon: Icon, title, body, action, className }: { icon?: LucideIcon; title: string; body?: React.ReactNode; action?: React.ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-start gap-2 rounded-md border border-dashed border-border-strong px-5 py-6", className)}>
      {Icon ? <Icon className="size-4 text-fg-subtle" aria-hidden /> : null}
      <div>
        <p className="text-sm font-medium">{title}</p>
        {body ? <p className="mt-0.5 max-w-prose text-sm text-fg-muted">{body}</p> : null}
      </div>
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-sm bg-muted", className)} />;
}

export function LoadingState({ rows = 6, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("flex flex-col gap-2", className)} role="status" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-7" />
      ))}
    </div>
  );
}

export function ErrorState({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  const apiError = error instanceof ApiError ? error : null;
  const message = apiError?.message ?? (error instanceof Error ? error.message : "Something went wrong.");
  return (
    <div role="alert" className={cn("flex items-start gap-3 rounded-md border border-danger/30 bg-danger-bg px-4 py-3", className)}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-danger">{message}</p>
        {apiError?.requestId ? (
          <p className="mt-0.5 font-mono text-2xs text-fg-muted">
            {apiError.code} · request {apiError.requestId}
          </p>
        ) : null}
      </div>
      {onRetry ? (
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      ) : null}
    </div>
  );
}
