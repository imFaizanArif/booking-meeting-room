# ADR 0002: Server-Sent Events for real-time delivery

- Status: accepted

## Decision
The real-time gateway is **SSE** (`text/event-stream`), authenticated by a short-lived signed
token obtained from an authenticated REST call (`POST /api/v1/realtime/token`).

## Reason
All real-time traffic is server-to-client: execution events, approval queue changes, server
health. Clients send commands through REST, where validation, CSRF and auditing already
live. SSE has native reconnection and a `Last-Event-ID` header that maps directly to our
per-execution `seq`, so replay-after-reconnect needs no custom protocol. It passes through
HTTP proxies and needs no extra library in the browser.

## Trade-off
One HTTP connection per stream (HTTP/2 multiplexes them in production). `EventSource`
cannot set headers, so the token travels as a query parameter; it is single-purpose,
scoped to one workspace and expires after 120 seconds, and the gateway never logs query
strings.
