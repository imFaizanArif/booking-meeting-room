# Security

## Model

- **The backend is the only authority.** Permissions, tool policy and approvals are enforced
  in the service layer and the `ToolRouter`. The UI hides controls for convenience only.
- **No API executes tools.** Tools run only inside the worker through `ToolRouter`. An
  approval decision records intent and enqueues a resume; the worker re-checks the decision
  before executing.
- **Every tool call is policy-checked**, whatever the model was told. Tool output is passed to
  models only as delimited tool-result messages and agents are instructed to treat it as
  data, so prompt injection in tool output cannot skip approval.

## Authentication and sessions

Argon2id password hashes; server-side sessions (`user_sessions`, SHA-256 of the token);
`HttpOnly`, `SameSite=Lax`, `Secure` (production) cookies; CSRF double-submit header on every
mutation; login rate limits per IP and per email; uniform timing for unknown emails.
`Authenticator` is an interface so OIDC can be added.

## Authorization

Roles per workspace: viewer < operator < owner. Every query filters by `workspace_id`.
Owners only: LLM providers and keys, stdio MCP servers, secrets, members, notification
channels, webhook secrets. Approving needs operator. Executions started by a viewer cannot
call tools (policy `CallerPermission`).

## Secrets

- `LocalEnvelopeSecretManager`: random 256-bit data key per secret, AES-256-GCM; the data
  key is wrapped with `SECRETS_MASTER_KEY` (AES-256-GCM). Vault/AWS/GCP/Azure backends
  implement the same `SecretManager` protocol.
- Write-only API: responses expose `is_set` and a 4-character hint.
- Decrypted only in the worker at the moment of use (provider keys, MCP env and headers,
  webhook URLs) and every access is audited (`secret.accessed`, without the value).
- Never stored in snapshots (refs only), events, audit payloads, logs or error messages: every
  decrypted value is registered with the central `Redactor`, which masks it in structlog
  output, event payloads and audit payloads, alongside key-name based masking. Tests assert
  this.

## Outbound requests (SSRF)

Streamable HTTP/SSE MCP servers, provider base URLs and notification webhooks pass
`guard_url`: http/https only; the host is resolved and private, loopback, link-local,
multicast, reserved and unspecified addresses are refused unless the host or CIDR is listed in
`OUTBOUND_ALLOWLIST`. Redirects are not followed by notifiers.

## stdio MCP servers: risk

A stdio server is an arbitrary command executed **on the worker host with the worker's
privileges**. Mitigations:

- only owners can create or edit them;
- the exact command line is shown verbatim and must be confirmed before activation; changing
  the command clears the confirmation;
- the process gets only the configured env (from secrets) plus `PATH`, `HOME`, `LANG`,
  `LC_ALL`, `TMPDIR`, `VIRTUAL_ENV`;
- processes are capped per worker and terminated with their process tree on shutdown.

Run workers as an unprivileged user (the Docker image uses uid 10001), on hosts or containers
dedicated to agent work, without cloud credentials they do not need. Treat adding a stdio
server like granting shell access.

## Audit

`audit_events` is append-only: `UPDATE`, `DELETE` and `TRUNCATE` are rejected by triggers and
revoked from `PUBLIC` (and from the `agent_platform_app` role if it exists). Audited: logins
and failures, logouts, config changes (with field diffs), secret writes/accesses/deletes,
execution starts and controls, approval decisions (with argument diffs), tool executions and
denials, member changes, schedule fires. Payloads are redacted before insert.

## Web

Strict CORS allow-list; `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
`Referrer-Policy`; the web app talks to the API same-origin through a rewrite. Notifications
link to the approval page and never carry approve links.

## Reporting

Report vulnerabilities privately to the maintainers; do not open public issues for them.
