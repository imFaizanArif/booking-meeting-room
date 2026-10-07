"use client";

import { PageContainer } from "@/components/shell/page-container";
import { PageHeader } from "@/components/ui/page";
import { useMe } from "@/features/auth/queries";
import { ModelsSection } from "@/features/llm/models-section";
import { ProvidersSection } from "@/features/llm/providers-section";

export default function ModelsPage() {
  const role = useMe().data?.role;
  return (
    <PageContainer>
      <PageHeader
        title="Models"
        description="LLM providers, the models they offer, and what each model costs. Owners manage this configuration; operators can run connection tests."
      />
      <ProvidersSection role={role} />
      <ModelsSection role={role} />
    </PageContainer>
  );
}
