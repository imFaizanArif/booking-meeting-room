# Agent Platform

A self-hostable control plane for autonomous agent pipelines: configure LLM providers and
MCP servers as data, build pipelines as DAGs with bounded agent nodes, gate every write
behind human approval, and watch executions live. Durable by design: LangGraph checkpoints in
Supabase Postgres, idempotent tool calls, crash recovery that never re-runs a destructive action.

```
Next.js console ──REST/SSE──► FastAPI (validate, persist, enqueue)
                                   │ arq (Redis)
                        worker(s) ─┴─ LangGraph ─ LLM adapters (OpenAI · Anthropic · Gemini · Ollama · fake)
                                   │            └ ToolRouter ─ policy ─ HITL ─ MCP (stdio · Streamable HTTP · SSE)
                        scheduler ─┘ (enqueue only: schedules, timers, recovery, approval expiry)
Supabase (Postgres): config, versions, checkpoints, read model, tool calls, approvals, usage, append-only audit
```

## Database: Supabase

Supabase is the only supported database; there is no local Postgres. Create a Supabase project
(a dedicated one is best), copy the connection string from **Project Settings → Database**, and
put it in `DATABASE_URL`. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#database-supabase) for
the connection modes. Redis is still needed for the job queue and live updates.

## Quick start (Docker)

```bash
cp .env.example .env              # set DATABASE_URL to your Supabase connection string
docker compose --env-file .env -f infra/docker-compose.yml up --build
open http://localhost:3000        # admin@example.com / admin-password
```

Migrations and the demo seed run automatically against Supabase. The demo needs no API keys: an offline
fake provider is active, and OpenAI, Anthropic, Google Gemini and Ollama are seeded inactive until
you add keys on **Models**. To use Gemini: **Models → Google Gemini → Edit**, paste the API key from
Google AI Studio, **Test connection**, then activate it and pick `gemini-2.5-flash` or
`gemini-2.5-pro` as the default model (or per node).

## Quick start (local, no Docker)

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22 + pnpm 10, Redis 7,
and a Supabase project.

```bash
make install
cp .env.example apps/api/.env              # set DATABASE_URL (Supabase), SECRETS_MASTER_KEY etc.
make mock &                                # demo jobs MCP server (Streamable HTTP :8811)
make migrate                               # migrations + checkpoint tables + RLS + demo seed
make api & make worker & make scheduler &  # :8000
make web                                   # :3000
```

## The demo: Job Application Assistant

Trigger → search jobs (**Demo Jobs**, Streamable HTTP) → shortlist with model A (structured
output) → for each job in parallel: analyse it (model A), check availability (**Demo
Calendar**, stdio), find relevant repositories (**Demo GitHub**, stdio) → condition → an
agent on model B reads the job and proposes `submit_proposal` → the execution **pauses**
→ you approve, edit, reject or ask for a new proposal on **Approvals** → the proposal is
submitted exactly once → End.

Run it from **Pipelines → Job Application Assistant → Run**, then open the execution to watch
it live. Restart the worker while it waits for approval; it resumes from its checkpoint.

## Repository

| Path | What |
| --- | --- |
| `apps/api` | FastAPI API, arq worker, scheduler (one Python package `app`) |
| `apps/mock-mcp` | Deterministic demo MCP servers with idempotency-key support |
| `apps/web` | Next.js App Router console |
| `packages/api-client` | TypeScript types + client generated from the OpenAPI schema |
| `infra/` | Dockerfiles and compose files |
| `docs/` | Architecture, decisions (ADRs), database, API, MCP, development, security, deployment |

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Database](docs/DATABASE.md) · [API](docs/API.md) · [MCP](docs/MCP.md)
- [Development](docs/DEVELOPMENT.md) (including how to add a provider, MCP server, tool,
  node type or notification channel)
- [Security](docs/SECURITY.md) · [Deployment](docs/DEPLOYMENT.md) · [Frontend conventions](docs/FRONTEND.md)
