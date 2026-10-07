"use client";

import { usePathname } from "next/navigation";
import * as React from "react";

import { CommandPalette } from "@/components/shell/command-palette";
import { Sidebar } from "@/components/shell/sidebar";
import { LoadingState } from "@/components/ui/states";
import { useMe } from "@/features/auth/queries";
import { useWorkspaceStream } from "@/features/realtime/use-stream";
import { useUI } from "@/stores/ui";

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const me = useMe();
  const pathname = usePathname();
  const builder = /^\/pipelines\/[^/]+$/.test(pathname);
  useWorkspaceStream();
  React.useEffect(() => {
    let stored: string | null = null;
    try {
      stored = localStorage.getItem("ap-theme");
    } catch {
      /* ignore */
    }
    if (stored === "light" || stored === "dark" || stored === "system") useUI.setState({ theme: stored });
  }, []);

  if (me.isPending) {
    return (
      <div className="mx-auto max-w-sm p-12">
        <LoadingState rows={3} />
      </div>
    );
  }
  if (me.isError) return null; // the query cache redirects to /login on 401

  return (
    <div className="flex h-dvh overflow-hidden">
      <Sidebar collapsed={builder} />
      <main className="scrollbar-thin min-w-0 flex-1 overflow-y-auto">{children}</main>
      <CommandPalette />
    </div>
  );
}
