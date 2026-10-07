import type { Schemas } from "@/lib/api/client";

type Schedule = Pick<Schemas["ScheduleOut"], "kind" | "cron" | "interval_seconds" | "daily_time" | "timezone">;

const DAY_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAY_PLURAL = ["Sundays", "Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays"];

const pad = (n: number) => String(n).padStart(2, "0");
const isInt = (s: string) => /^\d+$/.test(s);

/** "Every 15 min", "Every hour", "Every 1 h 30 min", "Every day". */
export function describeInterval(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return "Interval not set";
  if (seconds % 86_400 === 0) {
    const d = seconds / 86_400;
    return d === 1 ? "Every day" : `Every ${d} days`;
  }
  if (seconds % 3600 === 0) {
    const h = seconds / 3600;
    return h === 1 ? "Every hour" : `Every ${h} hours`;
  }
  if (seconds % 60 === 0) {
    const m = seconds / 60;
    if (m < 60) return m === 1 ? "Every minute" : `Every ${m} min`;
    return `Every ${Math.floor(m / 60)} h ${m % 60} min`;
  }
  return `Every ${seconds} s`;
}

/** Parse the weekday field of a cron expression into a sorted day list (0 = Sunday), or null if too complex. */
function parseDays(field: string): number[] | null {
  const days = new Set<number>();
  for (const part of field.split(",")) {
    const range = part.match(/^(\d)-(\d)$/);
    if (range) {
      const a = Number(range[1]);
      const b = Number(range[2]);
      if (a > b || b > 7) return null;
      for (let d = a; d <= b; d++) days.add(d % 7);
    } else if (/^\d$/.test(part) && Number(part) <= 7) {
      days.add(Number(part) % 7);
    } else {
      return null;
    }
  }
  return [...days].sort((x, y) => x - y);
}

function describeDays(days: number[]): string {
  const key = days.join(",");
  if (key === "1,2,3,4,5") return "Weekdays";
  if (key === "0,6") return "Weekends";
  if (days.length === 7) return "Daily";
  if (days.length === 1) return DAY_PLURAL[days[0]!]!;
  return days.map((d) => DAY_SHORT[d]).join(", ");
}

/**
 * Human text for simple five-field cron expressions, or null when it is not simple enough
 * to say in a few words (the caller then shows the raw expression).
 */
export function describeCron(cron: string | null | undefined): string | null {
  if (!cron) return null;
  const parts = cron.trim().split(/\s+/);
  if (parts.length !== 5) return null;
  const [min, hour, dom, mon, dow] = parts as [string, string, string, string, string];

  // */N * * * *
  const everyMin = min.match(/^\*\/(\d+)$/);
  if (everyMin && hour === "*" && dom === "*" && mon === "*" && dow === "*") {
    const n = Number(everyMin[1]);
    return n === 1 ? "Every minute" : `Every ${n} min`;
  }
  if (min === "*" && hour === "*" && dom === "*" && mon === "*" && dow === "*") return "Every minute";
  if (!isInt(min) || Number(min) > 59) return null;

  // M * * * *  /  M */N * * *
  if (dom === "*" && mon === "*" && dow === "*") {
    if (hour === "*") return `Hourly at :${pad(Number(min))}`;
    const everyHour = hour.match(/^\*\/(\d+)$/);
    if (everyHour) return `Every ${everyHour[1]} hours at :${pad(Number(min))}`;
  }
  if (!isInt(hour) || Number(hour) > 23) return null;
  const at = `${pad(Number(hour))}:${pad(Number(min))}`;
  if (mon !== "*") return null;

  if (dom === "*") {
    if (dow === "*") return `Daily at ${at}`;
    const days = parseDays(dow);
    return days ? `${describeDays(days)} at ${at}` : null;
  }
  if (isInt(dom) && dow === "*") return `Monthly on day ${Number(dom)} at ${at}`;
  return null;
}

export interface ScheduleDescription {
  /** Human text, e.g. "Weekdays at 08:45". Null when only the raw cron string can be shown. */
  text: string | null;
  /** Raw cron expression, shown in mono when `text` is null. */
  cron: string | null;
  /** Timezone suffix, omitted for interval schedules (they do not depend on wall-clock time). */
  timezone: string | null;
}

export function describeSchedule(s: Schedule): ScheduleDescription {
  if (s.kind === "interval") return { text: describeInterval(s.interval_seconds), cron: null, timezone: null };
  if (s.kind === "daily") return { text: s.daily_time ? `Daily at ${s.daily_time}` : "Daily", cron: null, timezone: s.timezone };
  return { text: describeCron(s.cron), cron: s.cron, timezone: s.timezone };
}

/** One-line plain-text version, e.g. "Weekdays at 08:45 Europe/London". */
export function scheduleSummary(s: Schedule): string {
  const d = describeSchedule(s);
  return [d.text ?? d.cron ?? "", d.timezone].filter(Boolean).join(" ");
}

export const COMMON_TIMEZONES = [
  "UTC",
  "Europe/London",
  "Europe/Dublin",
  "Europe/Lisbon",
  "Europe/Paris",
  "Europe/Berlin",
  "Europe/Amsterdam",
  "Europe/Madrid",
  "Europe/Stockholm",
  "Europe/Warsaw",
  "Europe/Athens",
  "Europe/Istanbul",
  "Africa/Johannesburg",
  "Asia/Dubai",
  "Asia/Karachi",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Hong_Kong",
  "Asia/Shanghai",
  "Asia/Tokyo",
  "Australia/Sydney",
  "Pacific/Auckland",
  "America/Sao_Paulo",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Toronto",
] as const;
