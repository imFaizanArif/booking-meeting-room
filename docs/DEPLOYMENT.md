# Deployment

## Processes

| Process | Command | Scale |
| --- | --- | --- |
| api | `uvicorn app.main:app` | horizontally, stateless |
| worker | `python -m app.workers.worker` | horizontally; each holds its own MCP connections |
| scheduler | `python -m app.workers.scheduler` | 1–2 instances (safe to run several) |
| migrate | `python -m app.db.migrate` | once per release, before api/worker start |
| web | `node apps/web/server.js` (Next standalone) | horizontally |

Postgres 16 and Redis 7 are required. Redis holds only the job queue, pub/sub and rate-limit
buckets; losing it loses nothing durable (the scheduler re-enqueues from Postgres).

## Docker Compose (single host)

```bash
export SECRETS_MASTER_KEY=$(python -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
export REALTIME_TOKEN_SECRET=$(openssl rand -hex 32)
export CORS_ORIGINS='["https://agents.example.com"]' PUBLIC_WEB_URL=https://agents.example.com
docker compose -f infra/docker-compose.yml -f infra/docker-compose.prod.yml up -d --build
```

The production override disables the demo seed and the demo MCP server, requires secrets from
the environment, sets secure cookies and runs two workers and two schedulers. Put a TLS
terminating reverse proxy in front of `web` (port 3000). Only `web` needs to be public; it
proxies `/api/*` to `api`.

SSE note: make sure the proxy does not buffer `text/event-stream` responses
(nginx: `proxy_buffering off;` for `/api/v1/realtime/`).

## Keys

- `SECRETS_MASTER_KEY` must stay stable: losing it makes every stored secret unreadable.
  Rotation: decrypt with the old key and re-wrap data keys with the new one (each secret
  stores `key_version` for this).
- `REALTIME_TOKEN_SECRET` can be rotated at any time (tokens last 120 seconds).

## Database

Create a dedicated role for the app. If it is named `agent_platform_app`, the initial
migration revokes `UPDATE/DELETE/TRUNCATE` on `audit_events` from it; the triggers reject
those statements for every role regardless.

## Observability

- Logs: JSON (structlog) on stdout with `request_id`, `workspace_id`, `user_id`,
  `execution_id`, `pipeline_version_id`, `node_id`, `tool_call_id`. Secrets are redacted.
- Metrics: `GET /metrics` (Prometheus: request counts and latency). Scrape every api replica.
- Health: `GET /healthz` (liveness), `GET /readyz` (Postgres + Redis).
- Tracing: `opentelemetry-api` is a dependency; install an SDK and exporter to emit spans.
  Sentry/Grafana are configuration only.

## Upgrades

1. Build images. 2. Run `migrate`. 3. Roll api and web. 4. Roll workers: SIGTERM lets arq
finish in-flight jobs; executions interrupted anyway are recovered from their checkpoint by the
scheduler once the lease expires (60 s), and non-read-only tool calls left in flight go to
human review instead of being retried.
