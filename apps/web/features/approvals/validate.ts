/**
 * Quick client-side check of edited tool arguments against the tool's JSON Schema
 * (required keys and top-level types). The server validates authoritatively.
 */
export interface ArgIssue {
  field: string;
  message: string;
}

type Schema = { type?: string | string[]; properties?: Record<string, Schema>; required?: string[]; enum?: unknown[] };

function typeOf(value: unknown): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (typeof value === "number") return Number.isInteger(value) ? "integer" : "number";
  return typeof value;
}

function matches(expected: string, actual: string): boolean {
  return expected === actual || (expected === "number" && actual === "integer");
}

export function parseArguments(text: string): { value?: Record<string, unknown>; error?: string } {
  try {
    const value: unknown = JSON.parse(text);
    if (value === null || typeof value !== "object" || Array.isArray(value)) return { error: "Arguments must be a JSON object" };
    return { value: value as Record<string, unknown> };
  } catch (e) {
    return { error: e instanceof Error ? e.message.replace(/^JSON\.parse: /, "") : "Invalid JSON" };
  }
}

export function checkArguments(schema: Schema | null | undefined, args: Record<string, unknown>): ArgIssue[] {
  if (!schema) return [];
  const issues: ArgIssue[] = [];
  for (const key of schema.required ?? []) {
    if (!(key in args)) issues.push({ field: key, message: "This field is required" });
  }
  for (const [key, value] of Object.entries(args)) {
    const prop = schema.properties?.[key];
    if (!prop) continue;
    const types = Array.isArray(prop.type) ? prop.type : prop.type ? [prop.type] : [];
    if (types.length && !types.some((t) => matches(t, typeOf(value)))) {
      issues.push({ field: key, message: `Expected ${types.join(" or ")}, got ${typeOf(value)}` });
    }
    if (prop.enum && !prop.enum.includes(value)) issues.push({ field: key, message: "Not one of the allowed values" });
  }
  return issues;
}
