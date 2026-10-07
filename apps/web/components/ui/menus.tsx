"use client";

import * as DropdownPrimitive from "@radix-ui/react-dropdown-menu";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import * as React from "react";

import { cn } from "@/lib/utils";

const floating =
  "anim-pop z-50 rounded-md border border-border bg-surface shadow-[0_8px_24px_-12px_oklch(0.2_0.02_255/0.35)]";

export const TooltipProvider = TooltipPrimitive.Provider;

export function Tooltip({ content, children, side = "top" }: { content: React.ReactNode; children: React.ReactElement; side?: "top" | "bottom" | "left" | "right" }) {
  return (
    <TooltipPrimitive.Root delayDuration={350}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content side={side} sideOffset={6} className="z-50 max-w-xs rounded-sm bg-ink px-2 py-1 text-xs text-ink-fg">
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}

export const DropdownMenu = DropdownPrimitive.Root;
export const DropdownMenuTrigger = DropdownPrimitive.Trigger;

export function DropdownMenuContent({ className, align = "end", ...props }: DropdownPrimitive.DropdownMenuContentProps) {
  return (
    <DropdownPrimitive.Portal>
      <DropdownPrimitive.Content align={align} sideOffset={4} className={cn(floating, "min-w-40 p-1", className)} {...props} />
    </DropdownPrimitive.Portal>
  );
}

export function DropdownMenuItem({ className, tone, ...props }: DropdownPrimitive.DropdownMenuItemProps & { tone?: "danger" }) {
  return (
    <DropdownPrimitive.Item
      className={cn(
        "flex cursor-default select-none items-center gap-2 rounded-sm px-2 py-1.5 text-sm outline-none data-[disabled]:opacity-50 data-[highlighted]:bg-subtle [&_svg]:size-3.5 [&_svg]:text-fg-subtle",
        tone === "danger" && "text-danger [&_svg]:text-danger",
        className,
      )}
      {...props}
    />
  );
}

export function DropdownMenuSeparator() {
  return <DropdownPrimitive.Separator className="my-1 h-px bg-border" />;
}

export const Popover = PopoverPrimitive.Root;
export const PopoverTrigger = PopoverPrimitive.Trigger;
export function PopoverContent({ className, align = "start", ...props }: PopoverPrimitive.PopoverContentProps) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content align={align} sideOffset={4} className={cn(floating, "p-3", className)} {...props} />
    </PopoverPrimitive.Portal>
  );
}

export const Tabs = TabsPrimitive.Root;
export function TabsList({ className, ...props }: TabsPrimitive.TabsListProps) {
  return <TabsPrimitive.List className={cn("flex items-center gap-4 border-b border-border", className)} {...props} />;
}
export function TabsTrigger({ className, ...props }: TabsPrimitive.TabsTriggerProps) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "-mb-px inline-flex h-8 items-center gap-1.5 border-b-2 border-transparent px-0.5 text-sm text-fg-muted transition-colors duration-100",
        "hover:text-fg data-[state=active]:border-fg data-[state=active]:text-fg",
        className,
      )}
      {...props}
    />
  );
}
export const TabsContent = TabsPrimitive.Content;
