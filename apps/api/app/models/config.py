"""Configuration entities: secrets, providers, models, MCP servers/tools, prompts, channels."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import (
    IsolationMode,
    NotificationChannelType,
    ProviderType,
    RiskLevel,
    ServerStatus,
    TransportType,
)
from app.db.base import Base, IdMixin, TimestampMixin, WorkspaceScoped, enum_col


class Secret(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    """Envelope-encrypted secret value. Other tables refer to it as `secret:<id>`."""

    __tablename__ = "secrets"
    __table_args__ = (sa.UniqueConstraint("workspace_id", "name"),)

    name: Mapped[str] = mapped_column(sa.String(200))
    description: Mapped[str | None] = mapped_column(sa.String(500))
    ciphertext: Mapped[bytes] = mapped_column(sa.LargeBinary)
    nonce: Mapped[bytes] = mapped_column(sa.LargeBinary)
    wrapped_data_key: Mapped[bytes] = mapped_column(sa.LargeBinary)
    key_nonce: Mapped[bytes] = mapped_column(sa.LargeBinary)
    key_version: Mapped[int] = mapped_column(default=1)
    hint: Mapped[str] = mapped_column(sa.String(8))
    version: Mapped[int] = mapped_column(default=1)
    rotated_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    managed: Mapped[bool] = mapped_column(
        default=False, server_default=sa.false(), comment="created implicitly for a config field"
    )


class LLMProvider(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "llm_providers"
    __table_args__ = (sa.UniqueConstraint("workspace_id", "name"),)

    name: Mapped[str] = mapped_column(sa.String(200))
    provider_type: Mapped[ProviderType] = mapped_column(enum_col(ProviderType, name="provider_type"))
    base_url: Mapped[str | None] = mapped_column(sa.String(500))
    api_key_secret_ref: Mapped[str | None] = mapped_column(sa.String(80))
    is_active: Mapped[bool] = mapped_column(default=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict, server_default="{}")
    requests_per_minute: Mapped[int | None]
    max_concurrency: Mapped[int | None]
    last_test_ok: Mapped[bool | None]
    last_test_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_test_message: Mapped[str | None] = mapped_column(sa.String(500))


class LLMModel(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "llm_models"
    __table_args__ = (sa.UniqueConstraint("provider_id", "model_name"),)

    provider_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("llm_providers.id", ondelete="CASCADE"), index=True
    )
    model_name: Mapped[str] = mapped_column(sa.String(200))
    display_name: Mapped[str] = mapped_column(sa.String(200))
    context_window: Mapped[int] = mapped_column(default=8192)
    supports_tools: Mapped[bool] = mapped_column(default=True)
    supports_streaming: Mapped[bool] = mapped_column(default=True)
    supports_json_schema: Mapped[bool] = mapped_column(default=True)
    default_parameters: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    input_price_per_mtok: Mapped[Decimal] = mapped_column(sa.Numeric(12, 6), default=Decimal(0))
    output_price_per_mtok: Mapped[Decimal] = mapped_column(sa.Numeric(12, 6), default=Decimal(0))
    is_active: Mapped[bool] = mapped_column(default=True)
    is_default: Mapped[bool] = mapped_column(default=False)


class MCPServer(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "mcp_servers"
    __table_args__ = (
        sa.UniqueConstraint("workspace_id", "slug"),
        sa.CheckConstraint(
            "(transport = 'stdio' AND command IS NOT NULL) OR (transport <> 'stdio' AND url IS NOT NULL)",
            name="transport_target",
        ),
    )

    name: Mapped[str] = mapped_column(sa.String(200))
    slug: Mapped[str] = mapped_column(sa.String(64))
    description: Mapped[str | None] = mapped_column(sa.Text)
    transport: Mapped[TransportType] = mapped_column(enum_col(TransportType, name="transport"))
    command: Mapped[str | None] = mapped_column(sa.String(500))
    args: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    cwd: Mapped[str | None] = mapped_column(sa.String(500))
    url: Mapped[str | None] = mapped_column(sa.String(1000))
    # name -> "secret:<id>" for values; plain non-secret values are not allowed here.
    env_refs: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    header_refs: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    isolation: Mapped[IsolationMode] = mapped_column(
        enum_col(IsolationMode, name="isolation"), default=IsolationMode.shared
    )
    status: Mapped[ServerStatus] = mapped_column(
        enum_col(ServerStatus, name="server_status"), default=ServerStatus.disconnected
    )
    status_message: Mapped[str | None] = mapped_column(sa.String(1000))
    is_active: Mapped[bool] = mapped_column(default=False)
    connect_timeout_s: Mapped[float] = mapped_column(default=20.0)
    call_timeout_s: Mapped[float] = mapped_column(default=60.0)
    requests_per_minute: Mapped[int | None]
    config_hash: Mapped[str] = mapped_column(sa.String(64), default="")
    last_connected_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    last_discovered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    command_confirmed_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class MCPTool(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "mcp_tools"
    __table_args__ = (sa.UniqueConstraint("server_id", "name"),)

    server_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("mcp_servers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(200))
    title: Mapped[str | None] = mapped_column(sa.String(300))
    description: Mapped[str | None] = mapped_column(sa.Text)
    input_schema: Mapped[dict[str, Any]] = mapped_column(default=dict)
    output_schema: Mapped[dict[str, Any] | None]
    annotations: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    schema_hash: Mapped[str] = mapped_column(sa.String(64))
    is_enabled: Mapped[bool] = mapped_column(default=False)
    is_read_only: Mapped[bool] = mapped_column(default=False)
    is_destructive: Mapped[bool] = mapped_column(default=False)
    requires_approval: Mapped[bool] = mapped_column(default=True)
    risk_level: Mapped[RiskLevel] = mapped_column(enum_col(RiskLevel, name="risk_level"), default=RiskLevel.medium)
    is_stale: Mapped[bool] = mapped_column(default=False)
    last_discovered_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class PromptTemplate(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "prompt_templates"
    __table_args__ = (sa.UniqueConstraint("workspace_id", "name"),)

    name: Mapped[str] = mapped_column(sa.String(200))
    description: Mapped[str | None] = mapped_column(sa.String(1000))
    latest_version: Mapped[int] = mapped_column(default=1)


class PromptTemplateVersion(IdMixin, TimestampMixin, Base):
    """Immutable body of one prompt template version."""

    __tablename__ = "prompt_template_versions"
    __table_args__ = (sa.UniqueConstraint("template_id", "version"),)

    template_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("prompt_templates.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    body: Mapped[str] = mapped_column(sa.Text)
    variables: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    created_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    change_note: Mapped[str | None] = mapped_column(sa.String(500))


class PromptVariable(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    """Workspace-level template variable, e.g. my_resume, target_hourly_rate. Never a secret."""

    __tablename__ = "prompt_variables"
    __table_args__ = (sa.UniqueConstraint("workspace_id", "key"),)

    key: Mapped[str] = mapped_column(sa.String(100))
    value: Mapped[str] = mapped_column(sa.Text)
    description: Mapped[str | None] = mapped_column(sa.String(500))


class NotificationChannel(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "notification_channels"
    __table_args__ = (sa.UniqueConstraint("workspace_id", "name"),)

    name: Mapped[str] = mapped_column(sa.String(200))
    channel_type: Mapped[NotificationChannelType] = mapped_column(
        enum_col(NotificationChannelType, name="channel_type")
    )
    url_secret_ref: Mapped[str] = mapped_column(sa.String(80))
    signing_secret_ref: Mapped[str | None] = mapped_column(sa.String(80))
    events: Mapped[list[Any]] = mapped_column(default=list, server_default="[]")
    is_active: Mapped[bool] = mapped_column(default=True)
    last_delivery_ok: Mapped[bool | None]
    last_delivery_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
