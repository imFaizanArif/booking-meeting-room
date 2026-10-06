"""Process configuration, loaded once from the environment."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str = "postgresql+asyncpg://postgres@localhost:5432/agent_platform"
    redis_url: str = "redis://localhost:6379/0"

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

    @property
    def sync_database_url(self) -> str:
        """psycopg URL used by the LangGraph checkpointer."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    return Settings()
