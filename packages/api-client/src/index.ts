/**
 * Typed client for the Agent Platform API. `schema.ts` is generated from the FastAPI
 * OpenAPI schema by `pnpm gen:client`; never edit it by hand.
 */
import createClient, { type Middleware } from "openapi-fetch";

import type { components, paths } from "./schema";

export type { components, paths } from "./schema";
export type Schemas = components["schemas"];
export type Schema<K extends keyof Schemas> = Schemas[K];

export interface FieldError {
  field: string;
  message: string;
}

/** Error thrown for every non-2xx response. Mirrors the server's ErrorEnvelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, requestId: string | null, details: Record<string, unknown>) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }

  get fields(): FieldError[] {
    const fields = this.details["fields"];
    return Array.isArray(fields) ? (fields as FieldError[]) : [];
  }
}

const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.slice(name.length + 1)) : null;
}

const csrf: Middleware = {
  onRequest({ request }) {
    if (UNSAFE.has(request.method)) {
      const token = readCookie("ap_csrf");
      if (token) request.headers.set("x-csrf-token", token);
    }
    return request;
  },
};

export function createApiClient(baseUrl = "") {
  const client = createClient<paths>({ baseUrl, credentials: "include" });
  client.use(csrf);
  return client;
}

export type ApiClient = ReturnType<typeof createApiClient>;

interface Envelope {
  error?: { code?: string; message?: string; request_id?: string | null; details?: Record<string, unknown> };
}

/** Unwrap an openapi-fetch result: return data or throw ApiError with the server's envelope. */
export function unwrap<T>(result: { data?: T; error?: unknown; response: Response }): T {
  if (result.response.ok && result.data !== undefined) return result.data;
  const body = (result.error ?? {}) as Envelope;
  const err = body.error ?? {};
  throw new ApiError(
    result.response.status,
    err.code ?? "INTERNAL_ERROR",
    err.message ?? `Request failed with status ${result.response.status}`,
    err.request_id ?? result.response.headers.get("x-request-id"),
    err.details ?? {},
  );
}
