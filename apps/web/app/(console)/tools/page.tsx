"use client";

import { PageContainer } from "@/components/shell/page-container";
import { useMe } from "@/features/auth/queries";
import { ToolsView } from "@/features/mcp/tools-view";

export default function ToolsPage() {
  const role = useMe().data?.role;
  return (
    <PageContainer>
      <ToolsView role={role} />
    </PageContainer>
  );
}
