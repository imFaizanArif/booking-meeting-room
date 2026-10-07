# ADR 0008: Structural changes to the suggested repository layout

- Status: accepted

## Decision
1. The platform was built in `agent-platform/` next to the existing meeting-room booking app,
   which was left untouched. The `agent-platform` branch carries only the platform, at the
   repository root, with no history shared with the booking app.
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
None left for (1): the split was done with `git subtree split`, and nothing inside the platform
depended on the folder name.
