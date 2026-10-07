# ADR 0009: Supabase is the only database

- Status: accepted

## Decision
The platform runs only against Supabase Postgres.
- `DATABASE_URL` is required and has no local default. The Postgres container is gone from
  Docker Compose. Pasted `postgresql://` strings get the asyncpg driver prefix.
- TLS and Supabase's transaction pooler (port 6543) are detected from the URL
  (`DATABASE_SSL`, `DATABASE_POOLER` override).
- `app.db.migrate` enables Row Level Security without policies on the platform's tables and
  revokes `anon`/`authenticated`, so the Data API cannot read them.
- Database tests use `TEST_DATABASE_URL`, a separate Supabase database, and drop only the
  platform's tables. Without it they are skipped.

## Reason
The team uses Supabase for every environment. One supported database means one tested
configuration, and Supabase-specific risks (the public Data API, PgBouncer's lack of prepared
statements) are handled in code instead of in setup notes.

## Trade-off
Database tests need network access and a second Supabase project or branch. Offline unit tests
still cover adapters, validation, expressions, policy and configuration.
