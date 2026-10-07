"""Supabase connection strings: driver prefix, TLS and pooler detection, and no local default."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings

DIRECT = "postgresql://postgres:pw@db.abcd.supabase.co:5432/postgres"
SESSION = "postgresql://postgres.abcd:pw@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"
TRANSACTION = "postgresql://postgres.abcd:pw@aws-0-eu-central-1.pooler.supabase.com:6543/postgres"


def settings(url: str, **extra: str) -> Settings:
    return Settings(_env_file=None, database_url=url, **extra)  # type: ignore[call-arg]


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)  # type: ignore[call-arg]


@pytest.mark.parametrize("url", [DIRECT, DIRECT.replace("postgresql://", "postgres://")])
def test_pasted_supabase_url_gets_the_asyncpg_driver(url: str) -> None:
    s = settings(url)
    assert s.database_url == "postgresql+asyncpg://postgres:pw@db.abcd.supabase.co:5432/postgres"
    assert s.sync_database_url == "postgresql://postgres:pw@db.abcd.supabase.co:5432/postgres?sslmode=require"


def test_non_postgres_url_is_rejected() -> None:
    with pytest.raises(ValidationError, match="Supabase Postgres connection string"):
        settings("mysql://user@host/db")


@pytest.mark.parametrize(("url", "pooler"), [(DIRECT, "none"), (SESSION, "session"), (TRANSACTION, "transaction")])
def test_supabase_modes_are_detected(url: str, pooler: str) -> None:
    s = settings(url)
    assert s.db_pooler == pooler
    assert s.db_ssl is True


def test_overrides_win_over_detection() -> None:
    s = settings(TRANSACTION, database_pooler="session", database_ssl="disable")
    assert s.db_pooler == "session"
    assert s.db_ssl is False
    assert "sslmode" not in s.sync_database_url
