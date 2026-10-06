# ADR 0003: Server-side sessions with HttpOnly cookies + CSRF double submit

- Status: accepted

## Decision
Email/password login (Argon2id). A successful login creates a row in `user_sessions`
(only the SHA-256 of the token is stored) and sets `ap_session` (HttpOnly, SameSite=Lax,
Secure in production). Unsafe methods require an `X-CSRF-Token` header equal to the
readable `ap_csrf` cookie. Authentication sits behind an `Authenticator` interface so OIDC
can be added as another implementation.

## Reason
The only client is our own web app served behind the same origin (Next.js rewrites
`/api/*` to FastAPI). Server-side sessions can be revoked instantly, and no token is
reachable from JavaScript. JWT + refresh adds rotation logic and cannot be revoked
without a denylist, which recreates server state.

## Trade-off
A database lookup per request (indexed by token hash, cheap). Third-party API clients
would need personal access tokens later; the `Authenticator` seam allows that.
