"use client";

import { useParams } from "next/navigation";

import { PipelineBuilder } from "@/features/pipelines/builder/builder";

export default function PipelinePage() {
  const { id } = useParams<{ id: string }>();
  return <PipelineBuilder id={id} />;
}
