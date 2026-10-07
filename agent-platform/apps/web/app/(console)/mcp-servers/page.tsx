"use client";

import * as React from "react";

import { PageContainer } from "@/components/shell/page-container";
import { LoadingState } from "@/components/ui/states";
import { useMe } from "@/features/auth/queries";
import { ServersView } from "@/features/mcp/servers-view";

export default function McpServersPage() {
  const role = useMe().data?.role;
  return (
    <PageContainer>
      {/* useSearchParams (?server=<id>) needs a Suspense boundary. */}
      <React.Suspense fallback={<LoadingState rows={5} />}>
        <ServersView role={role} />
      </React.Suspense>
    </PageContainer>
  );
}
