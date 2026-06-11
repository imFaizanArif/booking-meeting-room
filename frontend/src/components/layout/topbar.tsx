"use client";

import { LogOut, Menu, Plus, User } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { useMe } from "@/hooks/use-users";
import { createClient } from "@/lib/supabase/client";
import { useUiStore } from "@/stores/ui-store";
import { getInitials } from "@/lib/utils";

export function Topbar() {
  const router = useRouter();
  const { data: me } = useMe();
  const { toggleSidebar, openBookingDialog } = useUiStore();

  async function handleLogout() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <header className="glass sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-border/60 px-4 sm:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="lg:hidden"
        aria-label="Open menu"
        onClick={toggleSidebar}
      >
        <Menu className="h-5 w-5" />
      </Button>

      <div className="flex-1" />

      <Button size="sm" className="hidden sm:inline-flex" onClick={() => openBookingDialog()}>
        <Plus className="h-4 w-4" />
        Book a room
      </Button>
      <Button
        size="icon"
        className="sm:hidden"
        aria-label="Book a room"
        onClick={() => openBookingDialog()}
      >
        <Plus className="h-5 w-5" />
      </Button>

      <ThemeToggle />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            className="rounded-full ring-offset-background transition-shadow focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="Account menu"
          >
            <Avatar>
              <AvatarImage src={me?.avatar_url ?? undefined} alt={me?.name ?? "User"} />
              <AvatarFallback>{me ? getInitials(me.name || me.email) : "…"}</AvatarFallback>
            </Avatar>
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel>
            <p className="truncate text-sm font-semibold">{me?.name ?? "Loading…"}</p>
            <p className="truncate text-xs font-normal text-muted-foreground">{me?.email}</p>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem asChild>
            <Link href="/profile">
              <User />
              Profile
            </Link>
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={handleLogout} className="text-destructive">
            <LogOut />
            Log out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
