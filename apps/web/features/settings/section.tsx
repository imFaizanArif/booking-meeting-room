import { Lock } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

/** A settings section with a stable anchor id (linked from the side list and from other pages). */
export function SettingsSection({
  id,
  title,
  description,
  actions,
  children,
  className,
}: {
  id: string;
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className={cn("flex scroll-mt-6 flex-col gap-3 border-b border-border pb-8 last:border-b-0", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <h2 id={`${id}-title`} className="text-base font-semibold">
            {title}
          </h2>
          {description ? <p className="mt-0.5 max-w-[70ch] text-xs text-fg-muted">{description}</p> : null}
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function ReadOnlyNote({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-center gap-1.5 text-xs text-fg-subtle">
      <Lock className="size-3" aria-hidden />
      {children}
    </p>
  );
}
