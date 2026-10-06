# ADR 0001: arq as the async worker

- Status: accepted
- Date: 2026-10-06

## Decision
Executions run in **arq** workers (Redis-backed, asyncio-native). The scheduler is a separate
process that only enqueues arq jobs.

## Reason
The MCP SDK, LangGraph, httpx and SQLAlchemy async are asyncio-first. MCP stdio servers are
long-lived child processes owned by one event loop. arq runs every job as a coroutine on one
event loop per worker process, so MCP connections can be pooled per process and reused across
jobs. Celery's prefork model would need an event loop per task and cannot share stdio
connections across forked children.

## Trade-off
arq is smaller than Celery: no built-in canvas/chords, a simpler retry model, and fewer
monitoring tools. We do not need chords (LangGraph owns control flow), and retries are
handled by the execution engine with typed errors. Redis is a delivery mechanism only:
lost jobs are re-enqueued by the recovery sweep from Postgres (see ADR 0005).
