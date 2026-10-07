"use client";

import { useParams } from "next/navigation";
import * as React from "react";

import { ApprovalDesk } from "@/features/approvals/desk";

export default function ApprovalPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <React.Suspense>
      <ApprovalDesk selectedId={id} />
    </React.Suspense>
  );
}
