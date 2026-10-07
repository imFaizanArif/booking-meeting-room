"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as React from "react";
import { Toaster, toast } from "sonner";

import { TooltipProvider } from "@/components/ui/menus";
import { ApiError } from "@/lib/api/client";

function onUnauthenticated(error: unknown) {
  if (error instanceof ApiError && error.status === 401 && typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
  }
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 10_000,
            retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
            refetchOnWindowFocus: true,
          },
        },
        queryCache: new QueryCache({ onError: onUnauthenticated }),
        mutationCache: new MutationCache({
          onError: (error, _vars, _ctx, mutation) => {
            onUnauthenticated(error);
            if (mutation.meta?.silent) return;
            const message = error instanceof ApiError ? error.message : "The request failed.";
            toast.error(message, {
              description: error instanceof ApiError && error.requestId ? `Request ${error.requestId}` : undefined,
            });
          },
        }),
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <TooltipProvider>
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            className: "!rounded-md !border !border-border !bg-surface !text-fg !text-sm !shadow-[0_8px_24px_-12px_oklch(0.2_0.02_255/0.35)]",
          }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
