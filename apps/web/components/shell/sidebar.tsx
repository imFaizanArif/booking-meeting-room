"use client";

import { LogOut, Monitor, Moon, Search, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Kbd } from "@/components/ui/badge";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/menus";
import { usePendingCount } from "@/features/approvals/queries";
import { useLogout, useMe } from "@/features/auth/queries";
import { cn } from "@/lib/utils";
import { type Theme, useUI } from "@/stores/ui";

import { BRAND_ICON, NAV } from "./nav";

function isActive(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar() {
  const pathname = usePathname();
  const { data: me } = useMe();
  const pending = usePendingCount();
  const logout = useLogout();
  const { theme, setTheme, setPaletteOpen } = useUI();
  const Brand = BRAND_ICON;

  return (
    <aside className="flex h-full w-[216px] shrink-0 flex-col border-r border-border bg-subtle">
      <div className="flex h-12 items-center gap-2 px-4">
        <Brand className="size-4 text-fg" aria-hidden />
        <span className="text-sm font-semibold tracking-[-0.01em]">Agent Platform</span>
      </div>
      <div className="px-3 pb-2">
        <button
          type="button"
          onClick={() => setPaletteOpen(true)}
          className="flex h-7 w-full items-center gap-2 rounded-md border border-border bg-surface px-2 text-xs text-fg-subtle transition-colors duration-100 hover:border-border-strong hover:text-fg-muted"
        >
          <Search className="size-3.5" aria-hidden />
          <span className="flex-1 text-left">Jump to…</span>
          <Kbd>⌘K</Kbd>
        </button>
      </div>
      <nav className="scrollbar-thin flex-1 overflow-y-auto px-3 pb-3" aria-label="Main">
        {NAV.map((group) => (
          <div key={group.group} className="mt-3 first:mt-1">
            <p className="px-2 pb-1 text-2xs font-medium uppercase tracking-[0.06em] text-fg-subtle">{group.group}</p>
            <ul className="flex flex-col gap-px">
              {group.items.map((item) => {
                const active = isActive(pathname, item.href);
                const Icon = item.icon;
                const count = item.href === "/approvals" ? pending.data : undefined;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex h-7 items-center gap-2 rounded-md px-2 text-sm text-fg-muted transition-colors duration-100 hover:bg-muted hover:text-fg",
                        active && "bg-surface font-medium text-fg shadow-[0_0_0_1px_var(--border)]",
                      )}
                    >
                      <Icon className="size-3.5 shrink-0" aria-hidden />
                      <span className="flex-1 truncate">{item.label}</span>
                      {count ? (
                        <span className="tabular rounded-sm bg-warn-bg px-1.5 text-2xs font-semibold text-warn" aria-label={`${count} pending`}>
                          {count}
                        </span>
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>
      <div className="border-t border-border p-2">
        <DropdownMenu>
          <DropdownMenuTrigger className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-muted">
            <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-ink text-2xs font-semibold uppercase text-ink-fg">
              {me?.email?.[0] ?? "?"}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium">{me?.email ?? "…"}</span>
              <span className="block text-2xs capitalize text-fg-subtle">{me?.role}</span>
            </span>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-52">
            {(["light", "dark", "system"] as Theme[]).map((t) => (
              <DropdownMenuItem key={t} onSelect={() => setTheme(t)}>
                {t === "light" ? <Sun /> : t === "dark" ? <Moon /> : <Monitor />}
                <span className="flex-1 capitalize">{t} theme</span>
                {theme === t ? <span className="text-2xs text-fg-subtle">Active</span> : null}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => logout.mutate()}>
              <LogOut />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </aside>
  );
}
