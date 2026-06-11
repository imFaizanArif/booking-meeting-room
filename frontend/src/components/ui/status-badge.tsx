import { Badge } from "@/components/ui/badge";
import type { BookingStatus } from "@/lib/types";

const STATUS_CONFIG: Record<
  BookingStatus,
  { label: string; variant: "success" | "warning" | "destructive" | "secondary" }
> = {
  confirmed: { label: "Confirmed", variant: "success" },
  pending: { label: "Pending", variant: "warning" },
  rejected: { label: "Rejected", variant: "destructive" },
  cancelled: { label: "Cancelled", variant: "secondary" },
};

export function StatusBadge({ status }: { status: BookingStatus }) {
  const config = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  return <Badge variant={config.variant}>{config.label}</Badge>;
}
