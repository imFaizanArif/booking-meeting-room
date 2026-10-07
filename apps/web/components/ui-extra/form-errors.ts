import type { FieldValues, Path, UseFormSetError } from "react-hook-form";

import { ApiError } from "@/lib/api/client";

/**
 * Map `ApiError.fields` onto a React Hook Form. Fields the form knows get an inline
 * error; the rest (and the envelope message) are returned for a form-level alert.
 */
export function applyServerErrors<T extends FieldValues>(
  error: unknown,
  setError: UseFormSetError<T>,
  known: readonly string[],
  aliases: Record<string, string> = {},
): string | null {
  if (!(error instanceof ApiError)) return "Could not reach the server. Check your connection and try again.";
  const unmatched: string[] = [];
  let matched = 0;
  for (const f of error.fields) {
    const name = aliases[f.field] ?? f.field;
    if (known.includes(name)) {
      setError(name as Path<T>, { type: "server", message: f.message });
      matched += 1;
    } else {
      unmatched.push(`${f.field}: ${f.message}`);
    }
  }
  // Pydantic errors carry a generic envelope message; field errors alone say it better.
  if (matched > 0 && unmatched.length === 0 && error.message === "Some fields are invalid") return null;
  const suffix = unmatched.length ? ` (${unmatched.join("; ")})` : "";
  return `${error.message}${suffix}`;
}
