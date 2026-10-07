import * as React from "react";

import { cn } from "@/lib/utils";

export const controlClass =
  "w-full rounded-md border border-border-strong bg-surface px-2.5 text-sm text-fg placeholder:text-fg-subtle " +
  "transition-colors duration-100 hover:border-fg-subtle focus-visible:border-ring focus-visible:outline-none " +
  "focus-visible:ring-2 focus-visible:ring-ring/25 disabled:cursor-not-allowed disabled:opacity-60 " +
  "aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger/20";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(controlClass, "h-8", className)} {...props} />,
);
Input.displayName = "Input";

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea ref={ref} className={cn(controlClass, "min-h-20 py-1.5 leading-5", className)} {...props} />
  ),
);
Textarea.displayName = "Textarea";
