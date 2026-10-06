# ADR 0005: Checkpoints are the state; tables are a read model

- Status: accepted

## Decision
LangGraph's `AsyncPostgresSaver` owns resumable state (thread id = execution id).
`executions`, `execution_nodes`, `execution_events` and `tool_calls` are written by the
same worker right after each checkpointed step. Resume, retry and recovery always call
LangGraph with the thread id; they never reconstruct state from the read model.

Side-effect authority is separate: a `tool_calls` row keyed by a deterministic
idempotency key is inserted (`EXECUTING`) and committed **before** the MCP call and
updated after it. When a node is replayed from its checkpoint, completed calls are
reused from this table instead of being re-executed.

## Reason
LangGraph writes checkpoints through its own psycopg pool, so one cross-library
transaction is not available without patching the saver. The read model is therefore
eventually consistent with the checkpoint (milliseconds in practice), and drift is
recoverable: `execution_events` has a gap-free per-execution sequence, and the
`/executions/{id}/rebuild` admin action recomputes node rows from events and the
current checkpoint.

## Trade-off
A crash between checkpoint write and read-model write leaves the UI one step behind until
the execution is resumed by recovery, which rewrites the rows. We accept this; the
alternative (one DB writer for both) couples us to LangGraph internals.
