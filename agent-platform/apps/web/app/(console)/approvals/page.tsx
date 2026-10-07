"use client";

import * as React from "react";

import { ApprovalDesk } from "@/features/approvals/desk";

export default function ApprovalsPage() {
  return (
    <React.Suspense>
      <ApprovalDesk />
    </React.Suspense>
  );
}
