# Architecture

This document is the Phase 1 deliverable of the master build prompt, kept up to date as the
code evolves. Decisions are recorded as ADRs in [`docs/decisions/`](decisions/).

## 1. Runtime architecture

```
 Browser (Next.js app, generated TS client)
   |  REST  /api/v1/*  (same origin via Next rewrite, cookie session + CSRF)
   |  SSE   /api/v1/realtime/*?token=...  (short-lived signed token)
   v
 FastAPI "api" process ---------------------------+
   routers -> services -> repositories            |
   validates, authorizes, writes Postgres,        |   reads execution_events
   enqueues arq jobs. Never runs agent work.      |   + Redis pub/sub
   |                                              |
   | arq job (Redis list)            SSE gateway (inside the api process)
   v                                              ^
 "worker" process(es)  ---- EventBus.publish ----> Redis pub/sub channel  ws:{workspace}:*
   arq job -> ExecutionRunner                       (delivery optimisation only)
     LangGraph graph compiled from the pipeline version in the execution snapshot
       node executors: trigger | llm | agent | mcp_tool | condition | transform |
                       human_approval | notification | delay | end
       Agent subgraph: model step <-> tools step (bounded)
         LLMRegistry -> OpenAIAdapter | AnthropicAdapter | OllamaAdapter | FakeLLMProvider
         ToolRouter -> PolicyEngine -> (interrupt for approval) -> ToolExecutor
                        -> MCPConnectionManager (per process pool) -> stdio | streamable_http | sse_legacy
     AsyncPostgresSaver checkpoint after every super-step
   heartbeat lease on executions row

 "scheduler" process(es)
   every 5s: due schedules (FOR UPDATE SKIP LOCKED + unique (schedule_id, fire_at)) -> enqueue
   every 10s: due durable timers -> enqueue resume
   every 15s: recovery sweep (expired leases, orphaned QUEUED rows) -> re-enqueue
   every 60s: approval expiry -> reject + enqueue resume

 PostgreSQL: system of record (config, versions, checkpoints, read model, tool calls,
             approvals, usage, append-only audit, events)
 Redis:      arq queue, pub/sub, token buckets. Losing Redis loses nothing durable.
 SecretManager: envelope encryption in Postgres (AES-256-GCM data keys, master key from env).
```

Process roles share one Python package (`apps/api/app`) with three entrypoints:
`app.main:app` (uvicorn), `app.workers.worker` (arq) and `app.workers.scheduler`.

## 2. Repository structure

```
agent-platform/
  apps/
    api/                       Python package `app` (FastAPI, worker, scheduler)
      app/
        api/v1/                routers only (validation, auth dependency, mapping)
        core/                  config, logging (structlog + redaction), errors, security, ids, enums
        db/                    engine/session, base, migrations (alembic)
        models/                SQLAlchemy models
        schemas/               Pydantic DTOs (also the OpenAPI contract)
        services/              application use cases, authorization, transactions
        orchestration/         compiler, state, runner, node executors, expressions
        llm/                   protocol, canonical messages, adapters, registry, context, usage
        mcp/                   transports, connection manager, discovery, hashing
        tools/                 ToolRouter, policy engine, executor, audit
        hitl/                  approval decisions, edit validation, history rewrite
        prompts/               sandboxed template rendering
        events/                EventBus, event schemas, publisher
        realtime/              SSE gateway + token
        scheduler/             schedule computation, recovery sweeps
        notifications/         dispatcher + webhook/slack/discord notifiers
        secrets/               SecretManager + local envelope backend
        audit/                 append-only audit writer + redactor
        ratelimit/             Redis token buckets
        workers/               worker and scheduler entrypoints
        seed/                  demo data
      tests/{unit,integration,api}
    mock-mcp/                  demo MCP servers: jobs (streamable_http), calendar + github (stdio)
    web/                       Next.js App Router
      app/                     routes
      features/<domain>/       components, queries.ts, mutations.ts
      components/ui/           design system
      lib/api/                 thin wrappers around the generated client
      stores/                  Zustand (theme, command palette only)
  packages/
    api-client/                generated TS types + typed fetch client (openapi-typescript)
    config/                    shared tsconfig
  infra/docker/  infra/docker-compose.yml
  docs/  scripts/  Makefile  .env.example
```

## 3. Database

See [DATABASE.md](DATABASE.md) for the ERD, indexes and constraints.

## 4. Core domain model

### Enums (`app/core/enums.py`, exported to TypeScript through OpenAPI)

| Enum | Values |
| --- | --- |
| `Role` | owner, operator, viewer |
| `ProviderType` | openai, anthropic, ollama, fake |
| `TransportType` | stdio, streamable_http, sse_legacy |
| `ServerStatus` | disconnected, connecting, initializing, discovering, ready, reconnecting, failed |
| `IsolationMode` | shared, per_execution |
| `RiskLevel` | low, medium, high, critical |
| `NodeType` | trigger, llm, agent, mcp_tool, condition, transform, human_approval, notification, delay, end |
| `ExecutionStatus` | created, queued, running, waiting_for_tool, waiting_for_timer, paused_for_review, paused, resuming, completed, failed, cancelled |
| `NodeStatus` | pending, running, completed, failed, skipped, waiting, retrying, cancelled |
| `ToolCallStatus` | pending, awaiting_approval, approved, executing, completed, failed, rejected, cancelled, timeout, outcome_unknown |
| `ApprovalKind` | tool_call, data_review, outcome_unknown |
| `ApprovalStatus` | pending, approved, rejected, superseded, expired |
| `DecisionAction` | approve, edit, reject, regenerate, mark_succeeded, mark_failed, rerun |
| `PolicyDecision` | allow, deny, require_approval |
| `TriggerKind` | manual, schedule, webhook, restart |
| `EventType` | the 23 event types listed in section 5 |
| `ErrorCode` | central error code list (section 9) |

### Value objects
`IdempotencyKey(execution_id, node_id, call_seq)` (string form `exec:node:seq`, sha256 when
passed to servers), `SchemaHash` (sha256 of canonical JSON of input schema + annotations),
`NamespacedToolName` (`<server_slug>__<tool_name>`), `SecretRef` (`secret:<uuid>`),
`ConfigSnapshot`, `Money` (Decimal USD, 6dp).

### Execution state machine (`app/orchestration/state_machine.py`)

```
created  -> queued | cancelled
queued   -> running | cancelled | failed
running  -> waiting_for_tool | waiting_for_timer | paused_for_review | paused
            | completed | failed | cancelled | queued (recovery)
waiting_for_tool  -> running | failed | cancelled | queued (recovery)
waiting_for_timer -> resuming | cancelled
paused_for_review -> resuming | cancelled
paused            -> resuming | cancelled
resuming -> running | cancelled | failed | queued (recovery)
failed   -> resuming (retry from failed node)
completed, cancelled: terminal
```

Every status change goes through `transition(execution, new_status)`, which raises
`IllegalTransition` for anything not listed, and is applied with a compare-and-set UPDATE
(`WHERE status = :expected`) so concurrent writers cannot interleave.

### Tool call state machine

```
pending           -> awaiting_approval | executing | rejected | failed | cancelled
awaiting_approval -> approved | rejected | cancelled
approved          -> executing | cancelled
executing         -> completed | failed | timeout | outcome_unknown
failed            -> executing   (retryable error AND read-only tool only)
timeout           -> executing   (read-only tool only)
outcome_unknown   -> completed (mark succeeded) | failed (mark failed) | executing (explicit re-run)
completed, rejected, cancelled: terminal
```

## 5. API boundaries

All routes are under `/api/v1`, return the error envelope on failure, and are scoped to the
caller's workspace (from the session; a single default workspace ships).

| Resource | Endpoints |
| --- | --- |
| auth | `POST /auth/login`, `POST /auth/logout`, `GET /auth/me` |
| providers | `GET/POST /llm/providers`, `GET/PATCH/DELETE /llm/providers/{id}`, `POST /llm/providers/{id}/test` |
| models | `GET/POST /llm/models`, `PATCH/DELETE /llm/models/{id}`, `POST /llm/models/{id}/default` |
| mcp servers | `GET/POST /mcp/servers`, `GET/PATCH/DELETE /mcp/servers/{id}`, `POST .../test`, `POST .../discover`, `POST .../reconnect` |
| tools | `GET /mcp/tools`, `PATCH /mcp/tools/{id}`, `POST /mcp/tools/bulk` |
| prompts | `GET/POST /prompts`, `GET /prompts/{id}`, `POST /prompts/{id}/versions`, `POST /prompts/preview`, `GET/PUT/DELETE /prompt-variables` |
| pipelines | `GET/POST /pipelines`, `GET/PATCH/DELETE /pipelines/{id}`, `POST /pipelines/{id}/versions`, `GET /pipelines/{id}/versions/{vid}`, `POST /pipelines/validate`, `POST /pipelines/{id}/run`, `GET /node-types` |
| executions | `GET /executions`, `GET /executions/{id}` (+nodes, tool calls, usage, approvals), `GET /executions/{id}/events?after_seq=`, `POST .../pause|resume|cancel|retry|restart` |
| approvals | `GET /approvals`, `GET /approvals/{id}`, `POST /approvals/{id}/decision` |
| schedules | `GET/POST /schedules`, `PATCH/DELETE /schedules/{id}`, `GET /schedules/{id}/fires` |
| audit | `GET /audit` (filter by actor, type, entity, execution, time) |
| settings | `GET/PATCH /workspace`, `GET /members`, `PATCH /members/{user_id}`, `GET/POST/PATCH/DELETE /notification-channels`, `GET/PUT/DELETE /secrets` (write-only values) |
| dashboard | `GET /dashboard` |
| realtime | `POST /realtime/token`; SSE: `GET /realtime/executions/{id}?token=`, `GET /realtime/workspace?token=` |
| webhooks | `POST /hooks/pipelines/{pipeline_id}` (HMAC signed, for webhook triggers) |
| ops | `GET /healthz`, `GET /readyz`, `GET /metrics` |

### SSE contract
Each SSE message: `id: <seq>`, `event: <event_type>`, `data: <ExecutionEvent JSON>`.
On connect the gateway replays `execution_events` with `seq > Last-Event-ID` (or `?after_seq`),
then switches to live pub/sub, de-duplicating by `seq`. Workspace streams carry
`approval.*`, `execution.*` (status only) and `mcp.server_status_changed`, ids are
`<unix_ms>`, and missed workspace events are re-fetched through REST (they are
notifications, the queue itself is the record).

`ExecutionEvent = {id, execution_id, seq, type, node_id?, tool_call_id?, approval_id?,
payload (redacted), created_at}`.

## 6. MCP architecture

- **Transports** implement `MCPTransport.open() -> AsyncContextManager[(read, write)]`;
  a `TRANSPORTS: dict[TransportType, type[MCPTransport]]` registry resolves them.
  `streamable_http` uses `mcp.client.streamable_http.streamable_http_client` with an
  `httpx2.AsyncClient` carrying decrypted headers; `sse_legacy` uses `mcp.client.sse`;
  `stdio` uses `stdio_client` with the configured command, args and only the configured env.
- **Connection lifecycle**: `connecting -> initializing -> discovering -> ready`, plus
  `disconnected`, `reconnecting`, `failed`. Each connection is owned by one asyncio task
  that enters the transport and `ClientSession` contexts and holds them open until asked
  to close, so anyio cancel scopes are entered and exited in the same task.
- **Pool**: per worker process, keyed by `(server_id, config_hash, isolation_key)`.
  `isolation_key` is `"shared"` or the execution id when the server is `per_execution`.
  A config change produces a new hash: the old connection is retired once idle.
  A process-wide semaphore caps live stdio processes (`MCP_MAX_STDIO_PROCESSES`).
- **Health**: a background loop pings idle connections; failure moves the connection to
  `reconnecting` with exponential backoff and jitter, and to `failed` after N attempts.
  Status changes are written to `mcp_servers.status` and published as
  `mcp.server_status_changed`. One server failing never touches another's connection.
- **Discovery**: connect, initialize, `list_tools` following `next_cursor`, compute
  `schema_hash`, upsert `mcp_tools`, mark missing tools `is_stale`. New tools default to
  `is_enabled=false`; `requires_approval` defaults to `true` unless the server says
  `readOnlyHint: true`; `is_destructive` mirrors `destructiveHint` (annotations are hints).
  `notifications/tools/list_changed` triggers re-discovery when received.
- **Shutdown**: the worker closes every connection on SIGTERM; the stdio client
  terminates the process tree; `atexit` kills any leftovers.

## 7. Agent execution lifecycle

1. `POST /pipelines/{id}/run` validates input against the trigger schema, builds the
   **config snapshot** (pipeline version graph, per-node resolved LLM config with secret
   *refs*, prompt template bodies + versions, workspace variable values, enabled tool set
   with schemas, hashes and policy flags), inserts `executions` (`created -> queued`),
   audits, and enqueues `run_execution(execution_id)`.
2. The worker acquires a **lease** (`UPDATE executions SET lease_owner, lease_expires_at
   WHERE id = ? AND (lease_expires_at IS NULL OR lease_expires_at < now())`); a
   heartbeat extends it every 10s. Without the lease, the job exits.
3. `PipelineCompiler` turns the snapshot graph into a `StateGraph`:
   each pipeline node becomes one LangGraph node (Agent nodes become a compiled subgraph
   `model <-> tools`), each pipeline edge becomes an edge; a node with several incoming
   edges uses a waiting edge (`add_edge([a, b], c)`). Branch selection is data: every
   node computes whether it is *active* from its incoming edges (condition branch match,
   upstream not skipped); inactive nodes record `skipped` and pass through. This keeps
   joins deterministic without dynamic routing.
4. Graph state: `input`, `outputs{node_id: value}`, `node_status{node_id: status}`,
   `agents{node_id: AgentState}` (messages, iterations, tool call count, tokens),
   all with merge reducers so parallel branches never conflict.
5. The runner calls `graph.ainvoke(input | Command(resume=...) | None, config)` with
   `thread_id = execution_id`. The checkpointer stores a checkpoint after each step.
6. When `ainvoke` returns with `__interrupt__`, the runner classifies the interrupts
   (approval, operator pause, timer) and sets `paused_for_review`, `paused` or
   `waiting_for_timer`, then releases the lease. A paused execution holds no worker.
7. Resume: the decision service or timer enqueues `resume_execution`. The runner reads
   the pending interrupts from `aget_state`, resumes only those whose blocking condition
   is resolved (`Command(resume={interrupt_id: ...})`); the rest re-interrupt.
8. Recovery sweep: a `running`/`resuming` execution whose lease expired is recovered:
   its `executing` tool calls become `outcome_unknown` (or are reset for retry if the tool
   is read-only), the execution moves to `queued`, and `resume_execution` is enqueued. The
   resumed graph re-runs the interrupted node from its checkpoint; recorded tool calls are
   reused by idempotency key.
9. Cancellation sets `cancel_requested`; executors check it between steps and at every
   tool-call boundary and raise `ExecutionCancelled`.

## 8. HITL lifecycle

```
Agent tools step / MCP Tool node
  ToolRouter.route(call)
    tool_calls row (pending) keyed by idempotency key   <- reused if it already exists
    PolicyEngine.evaluate -> allow | deny | require_approval (+ reasons, risk)
    require_approval:
      tool_call -> awaiting_approval; approval(pending) created once
      events: tool.awaiting_approval, approval.created; NotificationDispatcher (async job)
      interrupt({"kind": "approval", "approval_id": ...})  -> checkpoint, worker released
Human decision (POST /approvals/{id}/decision)
  SELECT ... FOR UPDATE; status must be pending (else APPROVAL_ALREADY_DECIDED)
  operator role required; edit validated against the snapshot input schema
  approval + tool_call updated, audit (with diff), event, enqueue resume
Resume: node re-runs from checkpoint; ToolRouter sees the decided approval:
  approve -> execute stored arguments
  edit    -> rewrite the assistant tool-call message in the agent history to the edited
             arguments (original kept in approvals.original_arguments), then execute
  reject  -> no execution; tool result message {"rejected": true, "reason": ...};
             node config decides continue (default) or end
  regenerate -> approval superseded; the assistant message is replaced by a
             reviewer-feedback user message and the model step re-runs; the next proposed
             call for the same tool creates a new approval and the old one gets
             superseded_by = new id
```

**OUTCOME_UNKNOWN**: a recovered non-read-only call is set `outcome_unknown` and an
`outcome_unknown` approval is created in the same desk with three actions: mark succeeded
(operator supplies or confirms the result), mark failed, or re-run (requires
`confirm: true`). It is never re-executed automatically.

Expiry: approvals with `expires_at < now()` are resolved as `expired` (treated as reject)
by the scheduler sweep, which then enqueues the resume.

## 9. Security architecture

- **Auth**: ADR 0003. Argon2id, server-side sessions, CSRF double submit, login rate limit
  (Redis token bucket per IP + email), `Authenticator` interface for OIDC later.
- **Authorization**: `AuthContext(user, workspace, role)` is passed to every service
  call; services call `require_role(ctx, Role.operator)` etc. Queries always filter by
  `workspace_id`. Owners only: stdio MCP servers, secrets, members, provider keys.
- **Secrets**: `SecretManager` (`get`, `put`, `rotate`, `delete`) with `LocalEnvelopeSecretManager`:
  per-secret random 256-bit data key, AES-256-GCM for the value, data key wrapped with the
  master key (`SECRETS_MASTER_KEY`, 32 bytes base64). Other tables store `secret:<uuid>`
  refs. The API exposes `is_set` and a 4-char hint only. Decryption happens in the worker
  at use (MCP env/headers, provider keys, webhook URLs) and is audited as `secret.accessed`.
- **Redaction**: a central `Redactor` masks known secret values (registered when decrypted
  in-process) and sensitive key names (`password`, `token`, `api_key`, `authorization`,
  `secret`, ...); used by the structlog processor, the event publisher and the audit
  writer. Tests assert secret values never appear in API responses, logs, events, audit
  rows or snapshots.
- **SSRF**: outbound HTTP for Streamable HTTP/SSE servers, provider base URLs and webhooks
  is checked by `ssrf.guard_url`: scheme http/https only, DNS resolved, private,
  loopback, link-local, multicast and reserved ranges rejected unless the host or CIDR is in
  `OUTBOUND_ALLOWLIST`.
- **stdio risk**: commands run with the worker's privileges; owner-only, shown verbatim
  in a confirmation dialog before activation, env limited to configured values plus a
  minimal PATH/HOME, documented in SECURITY.md.
- **Headers/CORS**: strict CORS allow-list, `X-Content-Type-Options`, `X-Frame-Options:
  DENY`, `Referrer-Policy`, CSP on the web app.
- **Errors**: one envelope `{"error": {"code", "message", "request_id", "details"}}`; no
  stack traces to clients.

## 10. Key decisions

| ADR | Decision |
| --- | --- |
| [0001](decisions/0001-async-worker-arq.md) | arq async worker; scheduler only enqueues |
| [0002](decisions/0002-sse-for-realtime.md) | SSE with short-lived token and `Last-Event-ID` replay |
| [0003](decisions/0003-session-cookie-auth.md) | server-side session cookies + CSRF |
| [0004](decisions/0004-expression-language.md) | simpleeval + JSONPath for expressions |
| [0005](decisions/0005-read-model-consistency.md) | checkpoints are state; tables are a read model |
| [0006](decisions/0006-map-fanout-scope.md) | map fan-out inside a node; no mapped approvals |
| [0007](decisions/0007-llm-adapters-over-httpx.md) | adapters over httpx, no LiteLLM |
| [0008](decisions/0008-uv-workspace-layout.md) | layout changes vs. the prompt |

## 11. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Node re-execution on resume repeats side effects | idempotency key per call recorded before execution; completed calls reused; non-read-only calls never auto-retried; mock servers honour keys |
| Read model drifts from checkpoint | ADR 0005: events with gap-free seq, resume rewrites rows, rebuild action |
| Redis loss drops queued jobs/timers | recovery sweep re-enqueues from Postgres; timers live in `durable_timers` |
| Two schedulers fire twice | unique `(schedule_id, fire_at)` in `schedule_fires` + `FOR UPDATE SKIP LOCKED` |
| Double approval | row lock + status check; second decision gets `APPROVAL_ALREADY_DECIDED` |
| Prompt injection through tool output | tool output only in tool-result messages; policy evaluated on every call |
| Tool schema drift mid-execution | snapshot hash vs live hash at call time -> `TOOL_SCHEMA_CHANGED` |
| stdio servers run arbitrary commands | owner-only, verbatim confirmation, env allow-list, process cap |
| LangGraph / MCP SDK API churn | versions pinned; all usage behind `orchestration/` and `mcp/` modules |
| Runaway agent loops / cost | `max_iterations`, `max_tool_calls`, token budget per node, per-execution retry budget, rate limits |

## 12. Phase plan and acceptance criteria

| Phase | Acceptance |
| --- | --- |
| 1 Architecture | this document, DATABASE.md, ADRs |
| 2 Foundation | `make dev` boots api/web; migrations; login; error envelope; health; secrets; generated client compiles |
| 3 Walking skeleton | stdio mock server + fake LLM; gated tool pauses, survives worker restart, completes after approval (integration test) |
| 4 LLM layer | OpenAI/Anthropic/Ollama adapters with translation + error mapping unit tests; usage + cost; prompt preview; rate limits |
| 5 MCP layer | Streamable HTTP + stdio + legacy SSE; pool, health, stale detection, schema-hash check; isolation |
| 6 Execution & HITL | all node types; map; retries; OUTCOME_UNKNOWN; edit rewrite; regenerate; cancel; scheduler fire-once; notifications |
| 7 Frontend | all pages in section 12 of the prompt with loading/empty/error states |
| 8 Demo | Job Application Assistant seeded and runnable offline across 3 servers and 2 models |
| 9 Hardening | security tests, load script, metrics/tracing, docs, production compose profile |
