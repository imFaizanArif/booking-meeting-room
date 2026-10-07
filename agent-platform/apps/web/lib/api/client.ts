import { createApiClient } from "@agent-platform/api-client";

/** The single API client. Same origin: Next rewrites /api/* to the FastAPI service. */
export const api = createApiClient("");
export { ApiError, unwrap } from "@agent-platform/api-client";
export type { Schema, Schemas } from "@agent-platform/api-client";

