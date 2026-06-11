import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getInitials(name: string): string {
  return name
    .split(" ")
    .map((part) => part[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

export function formatTimeRange(start: string, end: string): string {
  const fmt = new Intl.DateTimeFormat("en", { hour: "numeric", minute: "2-digit" });
  return `${fmt.format(new Date(start))} – ${fmt.format(new Date(end))}`;
}

export function formatDate(date: string | Date): string {
  return new Intl.DateTimeFormat("en", {
    weekday: "short",
    month: "short",
    day: "numeric",
  }).format(new Date(date));
}
