"""Process configuration, loaded once from the environment."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True

    # Supabase is the only database. Paste the connection string from Project Settings -> Database;
    # `postgres://` / `postgresql://` are rewritten to the asyncpg driver.
    database_url: str = Field(description="Supabase Postgres connection string")
    redis_url: str = "redis://localhost:6379/0"
    # "auto" reads the Supabase URL: port 6543 = transaction pooler (no prepared statements),
    # and every *.supabase.co / *.supabase.com host needs TLS.
    database_pooler: Literal["auto", "none", "session", "transaction"] = "auto"
    database_ssl: Literal["auto", "disable", "require"] = "auto"
    database_pool_size: int = 10

    secrets_master_key: SecretStr = Field(
        default=SecretStr("ZGV2LW9ubHktbWFzdGVyLWtleS1jaGFuZ2UtbWUtMzI="),
        description="base64 encoded 32 byte key. The default is for local development only.",
    )
    realtime_token_secret: SecretStr = SecretStr("dev-only-realtime-secret-change-me")

    session_cookie_name: str = "ap_session"
    csrf_cookie_name: str = "ap_csrf"
    session_ttl_hours: int = 24 * 7
    cookie_secure: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]
    public_web_url: str = "http://localhost:3000"

    # Outbound request policy (SSRF). Hosts or CIDRs that may be private.
    outbound_allowlist: list[str] = Field(default_factory=list)

    mcp_max_stdio_processes: int = 16
    mcp_connect_timeout_s: float = 20.0
    mcp_health_interval_s: float = 30.0

    worker_lease_seconds: int = 60
    worker_heartbeat_seconds: int = 10
    worker_max_jobs: int = 20

    llm_default_timeout_s: float = 120.0
    login_rate_per_minute: int = 10
    mutation_rate_per_minute: int = 300

    seed_demo: bool = True
    demo_admin_email: str = "admin@example.com"
    demo_admin_password: SecretStr = SecretStr("admin-password")

    @field_validator("database_url")
    @classmethod
    def _asyncpg_scheme(cls, value: str) -> str:
        value = value.strip()
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value.removeprefix(prefix)
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must be a Supabase Postgres connection string (postgresql://...)")
        return value

    @property
    def sync_database_url(self) -> str:
        """psycopg URL used by the LangGraph checkpointer."""
        url = self.database_url.replace("postgresql+asyncpg://", "postgresql://")
        if self.db_ssl and "sslmode=" not in url:
            url += ("&" if "?" in url else "?") + "sslmode=require"
        return url

    @property
    def _db_host_port(self) -> tuple[str, int]:
        from urllib.parse import urlsplit

        parts = urlsplit(self.database_url.replace("postgresql+asyncpg://", "postgresql://"))
        return parts.hostname or "", parts.port or 5432

    @property
    def db_pooler(self) -> str:
        if self.database_pooler != "auto":
            return self.database_pooler
        host, port = self._db_host_port
        if port == 6543:
            return "transaction"
        return "session" if "pooler.supabase" in host else "none"

    @property
    def db_ssl(self) -> bool:
        if self.database_ssl != "auto":
            return self.database_ssl == "require"
        host, _ = self._db_host_port
        return "supabase.co" in host or "supabase.com" in host


@lru_cache
def get_settings() -> Settings:
    return Settings()
