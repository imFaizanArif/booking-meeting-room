# API

The FastAPI app serves its OpenAPI schema at `/openapi.json` and interactive docs at
`/docs`. All application routes are under `/api/v1`. The web app uses a TypeScript client
generated from that schema (`pnpm gen:client`; CI runs `pnpm check:client` and fails if
the committed client is stale).

## Conventions

- **Auth**: `POST /api/v1/auth/login` sets `ap_session` (HttpOnly) and `ap_csrf` cookies.
  Every `POST/PUT/PATCH/DELETE` needs header `x-csrf-token: <ap_csrf>`.
- **Errors**: always `{"error": {"code", "message", "request_id", "details"}}`. Codes come
  from `app.core.enums.ErrorCode` (`VALIDATION_ERROR`, `NOT_FOUND`, `FORBIDDEN`,
  `CSRF_FAILED`, `APPROVAL_ALREADY_DECIDED`, `TOOL_SCHEMA_CHANGED`, `MCP_CONNECTION_FAILED`,
  …). Field errors are `details.fields: [{field, message}]`; graph errors are
  `details.issues: [{message, node_id, edge_id, severity}]`.
- **Request ids**: send `x-request-id` or one is generated; it is echoed back and appears in
  logs, audit rows and error envelopes.
- **Roles**: viewer (read), operator (run, decide approvals, edit pipelines/prompts/tools,
  HTTP MCP servers), owner (providers, stdio MCP servers, secrets, members, channels).
- **Rate limits**: login 10/min per IP and per email; mutations 300/min per user;
  webhooks 60/min per IP. Exceeding returns 429 `RATE_LIMITED`.
- **Secrets are write-only**: responses show `{is_set, hint}` only.

## Endpoints

| Area | Endpoints |
| --- | --- |
| Auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| LLM | `GET/POST /llm/providers`, `PATCH/DELETE /llm/providers/{id}`, `POST /llm/providers/{id}/test`, `GET/POST /llm/models`, `PATCH/DELETE /llm/models/{id}`, `POST /llm/models/{id}/default` |
| MCP | `GET/POST /mcp/servers`, `GET/PUT/DELETE /mcp/servers/{id}`, `POST /mcp/servers/{id}/test`, `POST /mcp/servers/{id}/discover`, `POST /mcp/servers/{id}/reconnect`, `GET /mcp/tools`, `PATCH /mcp/tools/{id}`, `POST /mcp/tools/bulk` |
| Prompts | `GET/POST /prompts`, `GET/DELETE /prompts/{id}`, `POST /prompts/{id}/versions`, `POST /prompts/preview`, `GET/PUT /prompt-variables`, `DELETE /prompt-variables/{key}` |
| Pipelines | `GET /node-types`, `GET/POST /pipelines`, `POST /pipelines/validate`, `GET/PATCH/DELETE /pipelines/{id}`, `POST /pipelines/{id}/versions`, `GET /pipelines/{id}/versions/{n}`, `POST /pipelines/{id}/run`, `POST /pipelines/{id}/webhook-secret` |
| Executions | `GET /executions`, `GET /executions/{id}`, `GET /executions/{id}/events?after_seq=`, `POST /executions/{id}/control` (`pause`, `resume`, `cancel`, `retry`), `POST /executions/{id}/restart` |
| Approvals | `GET /approvals`, `GET /approvals/{id}`, `POST /approvals/{id}/decision` |
| Schedules | `GET/POST /schedules`, `PUT/DELETE /schedules/{id}`, `GET /schedules/{id}/fires` |
| Workspace | `GET /dashboard`, `GET /audit`, `GET/PATCH /workspace`, `GET/POST /members`, `PATCH /members/{user_id}`, `GET/POST /notification-channels`, `PUT/DELETE /notification-channels/{id}`, `GET/PUT /secrets`, `DELETE /secrets/{id}` |
| Realtime | `POST /realtime/token`; SSE `GET /realtime/executions/{id}?token=&after_seq=`, `GET /realtime/workspace?token=` |
| Webhook trigger | `POST /hooks/pipelines/{id}` with `X-Agent-Platform-Signature: t=<unix>,v1=<hmac>` |
| Ops | `GET /healthz`, `GET /readyz` (Postgres + Redis), `GET /metrics` (Prometheus) |

## Approval decisions

`POST /approvals/{id}/decision` body: `{"action": ..., ...}`

| Approval kind | Actions |
| --- | --- |
| `tool_call` | `approve`; `edit` with `edited_arguments` (validated against the snapshot schema); `reject` with `reason` (required); `regenerate` with optional `feedback` |
| `data_review` | `approve`; `edit` with `edited_data`; `reject` with `reason` |
| `outcome_unknown` | `mark_succeeded` with optional `result`; `mark_failed`; `rerun` with `confirm: true` |

Only `pending` approvals accept decisions (row lock). A second decision returns 409
`APPROVAL_ALREADY_DECIDED`. Deciding needs the operator role.

## Realtime (SSE)

1. `POST /api/v1/realtime/token` → `{token, expires_in: 120}`.
2. `new EventSource("/api/v1/realtime/executions/<id>?token=…&after_seq=<last seen>")`.
3. Each message: `id: <seq>`, `event: <type>`, `data: ExecutionEventOut`. The gateway first
   replays persisted events after `after_seq` (or `Last-Event-ID`), then relays live events,
   filling any pub/sub gap from Postgres. Event types are the `EventType` enum
   (`execution.*`, `node.*`, `llm.*`, `tool.*`, `approval.*`, `mcp.server_status_changed`).

## Webhook triggers

Generate a secret with `POST /pipelines/{id}/webhook-secret` (owner, shown once). Sign the raw
JSON body: `v1 = hex(hmac_sha256(secret, f"{t}.{body}"))`, header
`X-Agent-Platform-Signature: t=<unix seconds>,v1=<hex>`; requests older than 5 minutes are
rejected. The body becomes the execution input and is validated against the trigger schema.
