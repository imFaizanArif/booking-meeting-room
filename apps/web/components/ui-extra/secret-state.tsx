import { KeyRound } from "lucide-react";

import { cn } from "@/lib/utils";

/** "····abcd" from the API's write-only hint ("…abcd"), or "" when there is nothing to show. */
export function maskedHint(hint: string | null | undefined): string {
  const tail = (hint ?? "").replace(/^…/, "");
  return tail ? `····${tail}` : "";
}

/** Write-only secret state: never a value, only whether one is stored and its last characters. */
export function SecretState({
  state,
  setLabel = "Set",
  unsetLabel = "Not set",
  className,
}: {
  state: { is_set: boolean; hint?: string | null } | null | undefined;
  setLabel?: string;
  unsetLabel?: string;
  className?: string;
}) {
  if (!state?.is_set) return <span className={cn("text-xs text-fg-subtle", className)}>{unsetLabel}</span>;
  const hint = maskedHint(state.hint);
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-fg-muted", className)}>
      <KeyRound className="size-3 text-fg-subtle" aria-hidden />
      {setLabel}
      {hint ? <span className="font-mono text-fg">{hint}</span> : null}
    </span>
  );
}
