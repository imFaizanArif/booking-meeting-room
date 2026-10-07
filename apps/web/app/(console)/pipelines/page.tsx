"use client";

import * as React from "react";

import { PageContainer } from "@/components/shell/page-container";
import { LoadingState } from "@/components/ui/states";
import { PipelineList } from "@/features/pipelines/pipeline-list";

export default function PipelinesPage() {
  return (
    <React.Suspense
      fallback={
        <PageContainer>
          <LoadingState rows={6} />
        </PageContainer>
      }
    >
      <PipelineList />
    </React.Suspense>
  );
}
