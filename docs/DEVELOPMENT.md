# Development

## Setup

```bash
make install                    # uv sync (Python workspace) + pnpm install
cp .env.example apps/api/.env   # see settings below
make mock                       # Demo Jobs MCP server on :8811 (Streamable HTTP)
make migrate                    # alembic upgrade + LangGraph checkpoint tables + demo seed
make api worker scheduler web   # each in its own terminal
```

Log in at http://localhost:3000 as `admin@example.com` / `admin-password` (owner),
`operator@example.com` / `operator-password` or `viewer@example.com` / `viewer-password`.

## Checks

| Command | What |
| --- | --- |
| `pnpm turbo run lint typecheck test` | Everything, both languages |
| `cd apps/api && uv run pytest` | Python unit, integration and API tests (needs Postgres + Redis) |
| `cd apps/api && uv run ruff check app tests && uv run mypy app` | Python lint and types |
| `cd apps/web && pnpm typecheck && pnpm lint && pnpm test` | Web types, lint, Vitest |
| `cd apps/web && pnpm e2e` | Playwright end-to-end demo run (stack must be running) |
| `pnpm check:client` | Fails if the generated API client is out of date |
| `make load-test` | 50 concurrent demo executions |

Integration tests use the database named by `DATABASE_URL` in `apps/api/tests/conftest.py`
(default `agent_platform_test`) and Redis db 5, start their own Streamable HTTP mock server
and spawn the stdio mock servers. Real-provider tests are opt-in (`-m real_llm` with
`OPENAI_API_KEY` / `ANTHROPIC_API_KEY` set).

## Settings (environment)

All settings are in `app/core/config.py` and listed in `.env.example`. Notable:

| Variable | Purpose |
| --- | --- |
| `SECRETS_MASTER_KEY` | base64 32-byte key wrapping every secret's data key. Required in production |
| `REALTIME_TOKEN_SECRET` | HMAC key for SSE tokens |
| `OUTBOUND_ALLOWLIST` | JSON list of hosts/CIDRs allowed to resolve to private addresses (SSRF guard) |
| `MOCK_JOBS_URL`, `MOCK_MCP_PYTHON`, `MOCK_MCP_STATE_DIR` | Demo server wiring used by the seed |
| `WORKER_LEASE_SECONDS`, `WORKER_HEARTBEAT_SECONDS` | Crash detection for running executions |
| `SEED_DEMO` | Seed demo data during `python -m app.db.migrate` |

## Changing the API

1. Change Pydantic schemas/routers in `apps/api`.
2. `pnpm gen:client` regenerates `packages/api-client/src/{openapi.json,schema.ts}`.
3. Fix TypeScript errors (`pnpm --filter @agent-platform/web typecheck`). Commit both.

New database fields: edit `app/models`, then
`cd apps/api && uv run alembic revision --autogenerate -m "..."`, review the migration, and
`make migrate`.

## How to add…

### An LLM provider (no core changes)
Any OpenAI-compatible server: **Models → Add provider**, type `openai`, set the base URL and
key, add models. For a new API family:
1. Implement `generate`, `stream`, `health` in `app/llm/adapters/<name>.py`, translating the
   canonical messages in `app/llm/types.py` both ways and raising the typed errors in
   `app/llm/errors.py` (retry logic depends on the type).
2. Add a `ProviderType` value and register the adapter in `app/llm/registry.py`.
3. Add translation and error-mapping unit tests. Document what the provider cannot express.

### An MCP server
**MCP servers → Add server**. Choose the transport, fill in the command or URL and any
env/header secrets, activate (stdio requires confirming the exact command), then
**Discover tools**. No code change.

### A tool
Tools come from servers. After discovery, enable the tool on **Tools**, review its approval,
destructive and risk flags, then add it to an Agent node's allow-list or use it in an MCP Tool
node. Running executions keep the tool set from their snapshot.

### A node type
1. Add a value to `NodeType` (`app/core/enums.py`).
2. Add a config model and a node model in `app/schemas/pipeline_graph.py`, register it in
   `NODE_CONFIG_MODELS` and the `PipelineNode` union (and `MAPPABLE` if fan-out makes sense).
3. Implement an executor with `async run(node, rt, state, extra) -> output` in
   `app/orchestration/nodes/` and register it in `EXECUTORS` (`app/orchestration/compiler.py`).
   Use `interrupt()` only in a deterministic order (see `app/tools/router.py`).
4. Add validation rules in `app/orchestration/validation.py`, a label in
   `app/services/pipelines.py`, an icon in the web builder, then `pnpm gen:client`.

### A notification channel type
1. Add a `NotificationChannelType` value.
2. Implement `Notifier.send(url, message, signing_secret)` in
   `app/notifications/dispatcher.py` and add it to `NOTIFIERS`. Never include secrets or
   one-click approve links.
3. Channels are then configurable on **Settings → Notification channels**.
