"use client";

import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

import { controlClass } from "./input";

export interface SelectOption {
  value: string;
  label: React.ReactNode;
  description?: string;
  disabled?: boolean;
}

interface SelectProps {
  value: string | undefined;
  onValueChange: (value: string) => void;
  options: SelectOption[];
  placeholder?: string;
  id?: string;
  className?: string;
  disabled?: boolean;
  "aria-invalid"?: boolean;
  size?: "sm" | "md";
}

export function Select({ value, onValueChange, options, placeholder, id, className, disabled, size = "md", ...rest }: SelectProps) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectPrimitive.Trigger
        id={id}
        aria-invalid={rest["aria-invalid"]}
        className={cn(controlClass, "flex items-center justify-between gap-2 text-left", size === "sm" ? "h-7 text-xs" : "h-8", className)}
      >
        <SelectPrimitive.Value placeholder={<span className="text-fg-subtle">{placeholder ?? "Select"}</span>} />
        <SelectPrimitive.Icon>
          <ChevronDown className="size-3.5 text-fg-subtle" />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          position="popper"
          sideOffset={4}
          className="anim-pop z-50 max-h-72 min-w-[var(--radix-select-trigger-width)] overflow-hidden rounded-md border border-border bg-surface shadow-[0_8px_24px_-12px_oklch(0.2_0.02_255/0.35)]"
        >
          <SelectPrimitive.Viewport className="p-1">
            {options.map((opt) => (
              <SelectPrimitive.Item
                key={opt.value}
                value={opt.value}
                disabled={opt.disabled}
                className="relative flex cursor-default select-none flex-col rounded-sm py-1.5 pl-7 pr-2 text-sm outline-none data-[disabled]:opacity-50 data-[highlighted]:bg-subtle"
              >
                <SelectPrimitive.ItemIndicator className="absolute left-2 top-2">
                  <Check className="size-3.5" />
                </SelectPrimitive.ItemIndicator>
                <SelectPrimitive.ItemText>{opt.label}</SelectPrimitive.ItemText>
                {opt.description ? <span className="text-xs text-fg-subtle">{opt.description}</span> : null}
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
