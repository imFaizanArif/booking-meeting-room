import { AlertTriangle } from "lucide-react";
import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "@/lib/api/client";
import { cn } from "@/lib/utils";

/**
 * Map `ApiError.fields` onto a React Hook Form. `map` renames server field paths to form
 * field names (e.g. `interval_seconds` -> `interval_minutes`). Returns the fields that
 * could not be placed so the caller can show them in a banner.
 */
export function applyServerErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  known: readonly string[],
  map: Record<string, string> = {},
): { field: string; message: string }[] {
  if (!(error instanceof ApiError)) return [];
  const leftover: { field: string; message: string }[] = [];
  for (const f of error.fields) {
    const name = map[f.field] ?? f.field;
    if (known.includes(name)) setError(name as Path<T>, { type: "server", message: f.message });
    else leftover.push(f);
  }
  return leftover;
}

/** Inline error banner for a failed form submit. Shows the request id when there is one. */
export function FormError({ error, className }: { error: unknown; className?: string }) {
  if (!error) return null;
  const apiError = error instanceof ApiError ? error : null;
  const message = apiError?.message ?? (error instanceof Error ? error.message : "The request failed.");
  const extra = apiError?.fields.filter((f) => !f.field).map((f) => f.message) ?? [];
  return (
    <div role="alert" className={cn("flex items-start gap-2 rounded-md bg-danger-bg px-3 py-2 text-sm text-danger", className)}>
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <div className="min-w-0">
        <p>{message}</p>
        {extra.map((m) => (
          <p key={m} className="text-xs">
            {m}
          </p>
        ))}
        {apiError?.requestId ? <p className="mt-0.5 font-mono text-2xs text-fg-muted">request {apiError.requestId}</p> : null}
      </div>
    </div>
  );
}
