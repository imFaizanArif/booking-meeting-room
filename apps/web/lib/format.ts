import { formatDistanceToNowStrict, format } from "date-fns";

export function relativeTime(value: string | null | undefined): string {
  if (!value) return "—";
  return formatDistanceToNowStrict(new Date(value), { addSuffix: true });
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  return format(new Date(value), "d MMM yyyy, HH:mm:ss");
}

export function shortTime(value: string | null | undefined): string {
  if (!value) return "—";
  return format(new Date(value), "HH:mm:ss");
}

export function duration(start: string | null | undefined, end: string | null | undefined): string {
  if (!start) return "—";
  const ms = (end ? new Date(end).getTime() : Date.now()) - new Date(start).getTime();
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${Math.round(s % 60)}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export function ms(value: number | null | undefined): string {
  if (value == null) return "—";
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(2)} s`;
}

export function usd(value: string | number | null | undefined): string {
  const n = Number(value ?? 0);
  if (n === 0) return "$0.00";
  if (n < 0.01) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}

export function compact(n: number | null | undefined): string {
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(n ?? 0);
}

export function shortId(id: string | null | undefined): string {
  return id ? id.slice(-8) : "—";
}

export function humanize(value: string): string {
  return value.replace(/[_.]/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}
