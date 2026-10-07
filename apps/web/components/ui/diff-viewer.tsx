import { diffLines } from "diff";

import { cn } from "@/lib/utils";

/** Line diff of two values rendered as pretty JSON. */
export function DiffViewer({ before, after, className }: { before: unknown; after: unknown; className?: string }) {
  const a = typeof before === "string" ? before : JSON.stringify(before ?? {}, null, 2);
  const b = typeof after === "string" ? after : JSON.stringify(after ?? {}, null, 2);
  const parts = diffLines(a, b);
  const changed = parts.some((p) => p.added || p.removed);
  return (
    <div className={cn("scrollbar-thin overflow-auto rounded-md border border-border bg-surface font-mono text-xs leading-5", className)}>
      {!changed ? <p className="px-3 py-2 font-sans text-xs text-fg-muted">No changes.</p> : null}
      {parts.map((part, i) =>
        part.value
          .replace(/\n$/, "")
          .split("\n")
          .map((line, j) => (
            <div
              key={`${i}-${j}`}
              className={cn(
                "whitespace-pre-wrap break-all px-3",
                part.added && "bg-ok-bg text-ok",
                part.removed && "bg-danger-bg text-danger line-through decoration-danger/40",
                !part.added && !part.removed && "text-fg-muted",
              )}
            >
              <span className="mr-2 select-none text-fg-subtle">{part.added ? "+" : part.removed ? "−" : " "}</span>
              {line}
            </div>
          )),
      )}
    </div>
  );
}
