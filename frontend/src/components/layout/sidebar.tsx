"use client";

import {
  CalendarDays,
  ClipboardList,
  DoorOpen,
  LayoutDashboard,
  ShieldCheck,
  User,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AnimatePresence, motion } from "framer-motion";
import { Logo } from "@/components/layout/logo";
import { useMe } from "@/hooks/use-users";
import { useUiStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";

const NAV_ITEMS = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/rooms", label: "Rooms", icon: DoorOpen },
  { href: "/bookings", label: "My Bookings", icon: ClipboardList },
  { href: "/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/profile", label: "Profile", icon: User },
];

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data: me } = useMe();

  const items = [
    ...NAV_ITEMS,
    ...(me?.role === "admin"
      ? [{ href: "/admin", label: "Admin", icon: ShieldCheck }]
      : []),
  ];

  return (
    <nav className="flex flex-1 flex-col gap-1 px-3">
      {items.map(({ href, label, icon: Icon }) => {
        const active = pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={cn(
              "group relative flex items-center gap-3 rounded-2xl px-3.5 py-2.5 text-sm font-medium transition-all duration-200",
              active
                ? "text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            {active && (
              <motion.span
                layoutId="sidebar-active"
                className="absolute inset-0 rounded-2xl bg-primary shadow-lifted"
                transition={{ type: "spring", stiffness: 380, damping: 32 }}
              />
            )}
            <Icon className="relative z-10 h-[18px] w-[18px]" />
            <span className="relative z-10">{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

export function Sidebar() {
  const { sidebarOpen, setSidebarOpen } = useUiStore();

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col gap-6 border-r border-border/60 bg-card/60 py-6 backdrop-blur-xl lg:flex">
        <div className="px-6">
          <Logo />
        </div>
        <NavLinks />
        <p className="px-6 text-[11px] text-muted-foreground">
          © {new Date().getFullYear()} Kodifly
        </p>
      </aside>

      {/* Mobile drawer */}
      <AnimatePresence>
        {sidebarOpen && (
          <>
            <motion.div
              key="backdrop"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-secondary/40 backdrop-blur-sm lg:hidden"
              onClick={() => setSidebarOpen(false)}
            />
            <motion.aside
              key="drawer"
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 360, damping: 36 }}
              className="fixed inset-y-0 left-0 z-50 flex w-72 flex-col gap-6 border-r border-border/60 bg-card py-6 lg:hidden"
            >
              <div className="px-6">
                <Logo />
              </div>
              <NavLinks onNavigate={() => setSidebarOpen(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
