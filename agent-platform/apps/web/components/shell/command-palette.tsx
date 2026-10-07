"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Command } from "cmdk";
import { Moon, Play, Sun } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";

import { useUI } from "@/stores/ui";

import { ALL_NAV } from "./nav";

const item =
  "flex h-8 cursor-default select-none items-center gap-2 rounded-sm px-2 text-sm text-fg-muted data-[selected=true]:bg-subtle data-[selected=true]:text-fg [&_svg]:size-3.5";

export function CommandPalette() {
  const router = useRouter();
  const { paletteOpen, setPaletteOpen, setTheme } = useUI();

  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setPaletteOpen(!useUI.getState().paletteOpen);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setPaletteOpen]);

  function go(href: string) {
    setPaletteOpen(false);
    router.push(href);
  }

  return (
    <DialogPrimitive.Root open={paletteOpen} onOpenChange={setPaletteOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="anim-overlay fixed inset-0 z-40 bg-[var(--overlay)]" />
        <DialogPrimitive.Content className="anim-dialog fixed left-1/2 top-[16vh] z-50 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 overflow-hidden rounded-lg border border-border bg-surface shadow-[0_24px_48px_-24px_oklch(0.2_0.02_255/0.45)]">
          <DialogPrimitive.Title className="sr-only">Command palette</DialogPrimitive.Title>
          <Command loop>
            <Command.Input
              placeholder="Go to a page or run an action"
              className="h-10 w-full border-b border-border bg-transparent px-3 text-sm outline-none placeholder:text-fg-subtle"
            />
            <Command.List className="scrollbar-thin max-h-80 overflow-y-auto p-1">
              <Command.Empty className="px-3 py-4 text-sm text-fg-muted">No matches.</Command.Empty>
              <Command.Group heading="Pages" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-2xs [&_[cmdk-group-heading]]:text-fg-subtle">
                {ALL_NAV.map((nav) => {
                  const Icon = nav.icon;
                  return (
                    <Command.Item key={nav.href} value={`${nav.label} ${nav.keywords ?? ""}`} onSelect={() => go(nav.href)} className={item}>
                      <Icon />
                      {nav.label}
                    </Command.Item>
                  );
                })}
              </Command.Group>
              <Command.Group heading="Actions" className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1 [&_[cmdk-group-heading]]:text-2xs [&_[cmdk-group-heading]]:text-fg-subtle">
                <Command.Item value="new pipeline create" onSelect={() => go("/pipelines?new=1")} className={item}>
                  <Play />
                  New pipeline
                </Command.Item>
                <Command.Item value="dark theme" onSelect={() => { setTheme("dark"); setPaletteOpen(false); }} className={item}>
                  <Moon />
                  Dark theme
                </Command.Item>
                <Command.Item value="light theme" onSelect={() => { setTheme("light"); setPaletteOpen(false); }} className={item}>
                  <Sun />
                  Light theme
                </Command.Item>
              </Command.Group>
            </Command.List>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
