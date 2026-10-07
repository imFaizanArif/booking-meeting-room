import * as React from "react";

import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions, meta }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; meta?: React.ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 border-b border-border pb-4">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-[-0.01em]">{title}</h1>
        {description ? <p className="mt-1 max-w-[70ch] text-sm text-fg-muted">{description}</p> : null}
        {meta ? <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-fg-muted">{meta}</div> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function Section({ title, description, actions, children, className }: { title: React.ReactNode; description?: React.ReactNode; actions?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={cn("flex flex-col gap-3", className)}>
      <div className="flex items-end justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          {description ? <p className="mt-0.5 text-xs text-fg-muted">{description}</p> : null}
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function DescriptionList({ items, className }: { items: { label: string; value: React.ReactNode }[]; className?: string }) {
  return (
    <dl className={cn("grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 text-sm", className)}>
      {items.map((item) => (
        <React.Fragment key={item.label}>
          <dt className="text-fg-muted">{item.label}</dt>
          <dd className="min-w-0 break-words">{item.value}</dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

/** A number with a small label, used in metric strips (not oversized cards). */
export function Metric({ label, value, hint, tone }: { label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: "warn" | "danger" }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5 px-4 py-3">
      <span className="text-xs text-fg-muted">{label}</span>
      <span className={cn("tabular text-lg font-semibold", tone === "warn" && "text-warn", tone === "danger" && "text-danger")}>{value}</span>
      {hint ? <span className="text-2xs text-fg-subtle">{hint}</span> : null}
    </div>
  );
}

export function Panel({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("rounded-md border border-border bg-surface", className)}>{children}</div>;
}
