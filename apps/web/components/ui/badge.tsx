import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex h-5 items-center gap-1 whitespace-nowrap rounded-sm px-1.5 text-2xs font-medium [&_svg]:size-3",
  {
    variants: {
      tone: {
        neutral: "bg-muted text-fg-muted",
        info: "bg-info-bg text-info",
        warn: "bg-warn-bg text-warn",
        ok: "bg-ok-bg text-ok",
        danger: "bg-danger-bg text-danger",
        outline: "border border-border-strong text-fg-muted",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export type Tone = NonNullable<VariantProps<typeof badgeVariants>["tone"]>;

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-4 min-w-4 items-center justify-center rounded-[3px] border border-border-strong bg-surface px-1 font-mono text-[10px] text-fg-muted">
      {children}
    </kbd>
  );
}
