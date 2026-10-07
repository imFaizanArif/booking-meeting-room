"""Keep the platform's tables out of Supabase's Data API.

Supabase exposes the `public` schema over PostgREST to the `anon` and `authenticated` roles and,
by default, grants them privileges on new tables. This platform never uses the Data API: the API
server connects as the table owner and enforces workspace isolation itself. So each platform
table gets Row Level Security with no policies (the owner bypasses RLS; the Data API roles see
nothing) and the Data API roles lose their grants on it.

Only the platform's own tables are touched, so a Supabase project shared with another app keeps
working. Idempotent; runs after every migration (new tables only arrive through migrations).
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

DATA_API_ROLES = ("anon", "authenticated")
# Created by LangGraph's AsyncPostgresSaver.setup() and Alembic, not by our models.
EXTRA_TABLES = ("checkpoints", "checkpoint_writes", "checkpoint_blobs", "checkpoint_migrations", "alembic_version")


def platform_tables() -> list[str]:
    import app.models  # noqa: F401  (registers tables)
    from app.db.base import Base

    return sorted({*Base.metadata.tables, *EXTRA_TABLES})


async def lock_down(conn: AsyncConnection) -> list[str]:
    """Enable RLS on the platform's tables and revoke Data API access to them and their sequences.

    Returns the tables touched. Missing tables and roles are skipped.
    """
    tables = list(
        (
            await conn.execute(
                sa.text(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p') "
                    "AND c.relname = ANY(:names) ORDER BY 1"
                ),
                {"names": platform_tables()},
            )
        ).scalars()
    )
    sequences = list(
        (
            await conn.execute(
                sa.text(
                    "SELECT DISTINCT s.relname FROM pg_class s "
                    "JOIN pg_depend d ON d.objid = s.oid AND d.deptype IN ('a', 'i') "
                    "JOIN pg_class t ON t.oid = d.refobjid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace "
                    "WHERE s.relkind = 'S' AND n.nspname = current_schema() AND t.relname = ANY(:names)"
                ),
                {"names": tables},
            )
        ).scalars()
    )
    roles = sorted(
        (
            await conn.execute(
                sa.text("SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles)"), {"roles": list(DATA_API_ROLES)}
            )
        ).scalars()
    )
    for table in tables:
        await conn.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        for role in roles:
            await conn.execute(sa.text(f'REVOKE ALL ON TABLE "{table}" FROM {role}'))
    for sequence in sequences:
        for role in roles:
            await conn.execute(sa.text(f'REVOKE ALL ON SEQUENCE "{sequence}" FROM {role}'))
    return tables
