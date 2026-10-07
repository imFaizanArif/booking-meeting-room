import * as React from "react";

import { cn } from "@/lib/utils";

interface FieldProps {
  label: React.ReactNode;
  htmlFor?: string;
  hint?: React.ReactNode;
  error?: string | null;
  required?: boolean;
  className?: string;
  children: React.ReactNode;
  aside?: React.ReactNode;
}

/** Label + control + hint/error. Errors replace the hint so the layout does not jump twice. */
export function Field({ label, htmlFor, hint, error, required, className, children, aside }: FieldProps) {
  const describedBy = htmlFor ? `${htmlFor}-desc` : undefined;
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <div className="flex items-baseline justify-between gap-2">
        <label htmlFor={htmlFor} className="text-xs font-medium text-fg">
          {label}
          {required ? <span className="ml-0.5 text-fg-subtle" aria-hidden>*</span> : null}
        </label>
        {aside}
      </div>
      {children}
      {error ? (
        <p id={describedBy} role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={describedBy} className="text-xs text-fg-subtle">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

export function FieldRow({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cn("grid grid-cols-1 gap-3 sm:grid-cols-2", className)}>{children}</div>;
}
