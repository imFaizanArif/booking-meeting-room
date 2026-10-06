# ADR 0006: Fan-out (`map`) runs inside a node; interrupting nodes cannot be mapped

- Status: accepted

## Decision
`map` is executed inside one LangGraph node with an `asyncio.Semaphore(concurrency)`.
It is allowed on LLM, MCP Tool, Transform and Notification nodes. Agent and Human
Approval nodes cannot be mapped (rejected by the validator). If a mapped MCP Tool call
needs approval at run time, the item fails with `APPROVAL_NOT_ALLOWED_IN_MAP` and the
node error policy applies.

## Reason
Approval inside fan-out means N independent interrupts per node and per-item resume
bookkeeping. LangGraph `Send` could model it, but it multiplies checkpoint volume and
makes the UI and the integrity rules much harder to reason about. The demo and the
common cases fan out read-only work, then converge on one approval-gated step.

## Trade-off
"Approve each item separately" patterns need a map over items followed by an Agent node
that processes the list with approvals, rather than a mapped approval.
