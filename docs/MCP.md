# MCP integration

Built on the official MCP Python SDK (`mcp==2.3.0`, verified against the installed package:
`stdio_client`, `streamable_http_client(url, http_client=httpx2.AsyncClient)`, `sse_client`,
`ClientSession.call_tool(..., meta=...)`).

## Transports

| Transport | Use | Config |
| --- | --- | --- |
| `stdio` | Local servers spawned by the worker | `command`, `args`, `cwd`, `env` (secrets). Only `PATH`, `HOME`, `LANG`, `LC_ALL`, `TMPDIR`, `VIRTUAL_ENV` are inherited from the worker |
| `streamable_http` | Primary remote transport | `url`, `headers` (secrets), timeouts. URL passes the SSRF guard |
| `sse_legacy` | Older HTTP+SSE servers only | `url`, `headers` |

A transport is one class in `app/mcp/transports.py` plus one `TransportType` value.

## Connections

- One `MCPConnection` per pool key `(server_id, config_hash, isolation_key)` per worker
  process, owned by a dedicated asyncio task (anyio cancel scopes must exit in the task that
  entered them). Calls from any task use the published `ClientSession`.
- Lifecycle `connecting → initializing → discovering → ready`, plus `reconnecting`,
  `failed`, `disconnected`; changes are written to `mcp_servers.status` and published as
  `mcp.server_status_changed`.
- `isolation: per_execution` gives each execution its own process, closed when the
  execution releases the worker.
- Editing a server changes its `config_hash`; idle connections with the old hash are retired.
- A semaphore caps live stdio processes per worker (`MCP_MAX_STDIO_PROCESSES`). The health
  loop pings idle connections and reconnects with exponential backoff; one failing server
  never affects another.

## Discovery

`Discover tools` (UI) or `POST /mcp/servers/{id}/discover` asks a worker to connect,
initialize, page through `tools/list`, compute `schema_hash` (sha256 of canonical JSON of the
input schema + annotations) and upsert `mcp_tools`. Tools missing from the listing become
`is_stale`. New tools start **disabled**; `requires_approval` defaults to true unless the
server sets `readOnlyHint: true`; `is_destructive` mirrors `destructiveHint`. Annotations
are hints: operators can change every flag, and re-discovery never overwrites their choices.
`notifications/tools/list_changed` triggers re-discovery automatically.

## Calling tools

Every call goes through `ToolRouter` (`app/tools/router.py`):

1. A `tool_calls` row is created with idempotency key `execution:node:seq` before anything
   runs; replays reuse it.
2. Arguments are validated against the snapshot schema (JSON Schema 2020-12).
3. The policy engine evaluates: tool exists → enabled → in allow-list → caller permission →
   live schema hash equals snapshot hash → approval requirement.
4. Gated calls create an approval and `interrupt()` the graph; the worker is released.
5. Execution sends `_meta.idempotency_key` (an opaque hash of the internal key). The demo
   servers honour it, returning the original result on a repeated key.
6. Read-only calls retry transport errors up to 3 times. Any other call that times out or
   loses its connection becomes `outcome_unknown` and goes to a human; it is never retried
   automatically.

Tool names exposed to models are `<server_slug>__<tool_name>`, so two servers can expose the
same tool name.

## Demo servers (`apps/mock-mcp`)

| Server | Transport in the demo | Tools |
| --- | --- | --- |
| Demo Jobs (`mock_mcp.jobs_server`) | Streamable HTTP (`--http --port 8811`) | `search_jobs`, `get_job`, `submit_proposal` (destructive) |
| Demo Calendar (`mock_mcp.calendar_server`) | stdio | `check_availability`, `create_event` |
| Demo GitHub (`mock_mcp.github_server`) | stdio | `list_repositories`, `get_repository`, `create_issue` |

Each server can run over either transport (`--http`). Side effects are recorded in
`$MOCK_MCP_STATE_DIR/<server>.json` keyed by idempotency key (file-locked across processes);
`mock_mcp.common.effects(server)` returns them for tests.
