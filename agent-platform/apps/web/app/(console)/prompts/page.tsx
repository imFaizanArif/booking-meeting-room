"use client";

import { Suspense } from "react";

import { PageContainer } from "@/components/shell/page-container";
import { useMe } from "@/features/auth/queries";
import { PromptStudio } from "@/features/prompts/prompt-studio";

export default function PromptsPage() {
  const role = useMe().data?.role;
  return (
    <PageContainer>
      <Suspense>
        <PromptStudio role={role} />
      </Suspense>
    </PageContainer>
  );
}
