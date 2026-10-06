# ADR 0008: Structural changes to the suggested repository layout

- Status: accepted

## Decision
1. The platform lives in `agent-platform/` inside this repository so the existing meeting-room
   booking app is preserved untouched.
2. The Python side is a **uv workspace** (`apps/api`, `apps/mock-mcp`) with one lockfile.
3. `apps/api/app/hitl/` holds approval decision logic; `apps/api/app/orchestration/nodes/`
   holds one module per node type; `apps/api/app/realtime/` holds the SSE gateway (the
   prompt's `events/` keeps the bus and schemas).
4. Added tables beyond the prompt's list: `user_sessions`, `prompt_template_versions`,
   `schedule_fires`, `execution_events`, `durable_timers`, `notification_channels`.

## Reason
(1) "Preserve working code". (2) mock servers and the API share the MCP SDK pin and run
from one virtualenv in dev and in the worker image. (3)/(4) Each is a concrete requirement of
the prompt (session revocation, immutable prompt versions, fire-once proof, gap-free
replay, durable delays, channel config).

## Trade-off
Two levels of nesting in the repo. A future split can move `agent-platform/` to its own
repository with `git filter-repo` without changing anything inside it.
