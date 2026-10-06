"""DTOs for configuration resources. Secret values are write-only everywhere."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from app.core.enums import (
    IsolationMode,
    NotificationChannelType,
    ProviderType,
    RiskLevel,
    Role,
    ServerStatus,
    TransportType,
)
from app.schemas.common import ORM, SecretFieldState

# ---- LLM providers & models ------------------------------------------------------------------


class ProviderIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    provider_type: ProviderType
    base_url: str | None = Field(default=None, max_length=500)
    api_key: str | None = Field(default=None, description="Write-only. Omit to keep the current key.")
    clear_api_key: bool = False
    is_active: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    requests_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    max_concurrency: int | None = Field(default=None, ge=1, le=1000)


class ProviderPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    base_url: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    is_active: bool | None = None
    metadata: dict[str, Any] | None = None
    requests_per_minute: int | None = Field(default=None, ge=1, le=100_000)
    max_concurrency: int | None = Field(default=None, ge=1, le=1000)


class ProviderOut(ORM):
    id: uuid.UUID
    name: str
    provider_type: ProviderType
    base_url: str | None
    api_key: SecretFieldState
    is_active: bool
    metadata: dict[str, Any]
    requests_per_minute: int | None
    max_concurrency: int | None
    last_test_ok: bool | None
    last_test_at: datetime | None
    last_test_message: str | None
    model_count: int = 0
    created_at: datetime
    updated_at: datetime


class ModelIn(BaseModel):
    provider_id: uuid.UUID
    model_name: str = Field(min_length=1, max_length=200)
    display_name: str = Field(min_length=1, max_length=200)
    context_window: int = Field(default=8192, ge=512, le=10_000_000)
    supports_tools: bool = True
    supports_streaming: bool = True
    supports_json_schema: bool = True
    default_parameters: dict[str, Any] = Field(default_factory=dict)
    input_price_per_mtok: Decimal = Field(default=Decimal(0), ge=0)
    output_price_per_mtok: Decimal = Field(default=Decimal(0), ge=0)
    is_active: bool = True


class ModelPatch(BaseModel):
    model_name: str | None = None
    display_name: str | None = None
    context_window: int | None = Field(default=None, ge=512, le=10_000_000)
    supports_tools: bool | None = None
    supports_streaming: bool | None = None
    supports_json_schema: bool | None = None
    default_parameters: dict[str, Any] | None = None
    input_price_per_mtok: Decimal | None = Field(default=None, ge=0)
    output_price_per_mtok: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ModelOut(ORM):
    id: uuid.UUID
    provider_id: uuid.UUID
    provider_name: str = ""
    provider_type: ProviderType | None = None
    model_name: str
    display_name: str
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    supports_json_schema: bool
    default_parameters: dict[str, Any]
    input_price_per_mtok: Decimal
    output_price_per_mtok: Decimal
    is_active: bool
    is_default: bool


class TestResult(BaseModel):
    ok: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


# ---- MCP servers & tools ---------------------------------------------------------------------


class MCPServerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, pattern=r"^[a-z][a-z0-9_]{1,40}$")
    description: str | None = None
    transport: TransportType
    command: str | None = Field(default=None, max_length=500)
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    url: str | None = Field(default=None, max_length=1000)
    env: dict[str, str] = Field(default_factory=dict, description="Write-only values (stored as secrets)")
    env_keep: list[str] = Field(default_factory=list, description="Existing env names to keep unchanged")
    headers: dict[str, str] = Field(default_factory=dict, description="Write-only values (stored as secrets)")
    headers_keep: list[str] = Field(default_factory=list)
    isolation: IsolationMode = IsolationMode.shared
    is_active: bool = False
    connect_timeout_s: float = Field(default=20.0, ge=1, le=300)
    call_timeout_s: float = Field(default=60.0, ge=1, le=3600)
    requests_per_minute: int | None = Field(default=None, ge=1)
    confirm_command: bool = Field(default=False, description="Required to activate a stdio server")


class MCPServerOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
    transport: TransportType
    command: str | None
    args: list[str]
    cwd: str | None
    url: str | None
    env: dict[str, SecretFieldState]
    headers: dict[str, SecretFieldState]
    isolation: IsolationMode
    status: ServerStatus
    status_message: str | None
    is_active: bool
    connect_timeout_s: float
    call_timeout_s: float
    requests_per_minute: int | None
    last_connected_at: datetime | None
    last_discovered_at: datetime | None
    command_confirmed_at: datetime | None
    tool_count: int = 0
    enabled_tool_count: int = 0
    created_at: datetime
    updated_at: datetime


class MCPToolOut(ORM):
    id: uuid.UUID
    server_id: uuid.UUID
    server_slug: str = ""
    server_name: str = ""
    name: str
    namespaced_name: str = ""
    title: str | None
    description: str | None
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None
    annotations: dict[str, Any]
    schema_hash: str
    is_enabled: bool
    is_read_only: bool
    is_destructive: bool
    requires_approval: bool
    risk_level: RiskLevel
    is_stale: bool
    last_discovered_at: datetime | None


class MCPToolPatch(BaseModel):
    is_enabled: bool | None = None
    requires_approval: bool | None = None
    is_destructive: bool | None = None
    risk_level: RiskLevel | None = None


class MCPToolBulk(BaseModel):
    tool_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)
    patch: MCPToolPatch


class DiscoveryOut(BaseModel):
    ok: bool
    message: str
    added: list[str] = Field(default_factory=list)
    updated: list[str] = Field(default_factory=list)
    stale: list[str] = Field(default_factory=list)
    schema_changed: list[str] = Field(default_factory=list)


# ---- prompts -----------------------------------------------------------------------------------


class PromptTemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    body: str = Field(max_length=200_000)
    change_note: str | None = None


class PromptVersionIn(BaseModel):
    body: str = Field(max_length=200_000)
    change_note: str | None = Field(default=None, max_length=500)


class PromptVersionOut(ORM):
    id: uuid.UUID
    version: int
    body: str
    variables: list[str]
    change_note: str | None
    created_by: uuid.UUID | None
    created_at: datetime


class PromptTemplateOut(ORM):
    id: uuid.UUID
    name: str
    description: str | None
    latest_version: int
    latest_body: str = ""
    variables: list[str] = Field(default_factory=list)
    updated_at: datetime


class PromptTemplateDetail(PromptTemplateOut):
    versions: list[PromptVersionOut]


class PromptPreviewIn(BaseModel):
    body: str = Field(max_length=200_000)
    sample: dict[str, Any] = Field(default_factory=dict, description="Values for input/nodes/item or extra variables")


class PromptPreviewOut(BaseModel):
    rendered: str | None
    unresolved: list[str]
    error: str | None
    variables: list[str]


class PromptVariableIn(BaseModel):
    key: str = Field(pattern=r"^[a-z_][a-z0-9_]{0,99}$")
    value: str = Field(max_length=100_000)
    description: str | None = Field(default=None, max_length=500)


class PromptVariableOut(ORM):
    id: uuid.UUID
    key: str
    value: str
    description: str | None
    updated_at: datetime


# ---- settings ----------------------------------------------------------------------------------


class WorkspaceOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    settings: dict[str, Any]


class WorkspacePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    settings: dict[str, Any] | None = None


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    display_name: str
    role: Role
    last_login_at: datetime | None


class MemberIn(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+$", max_length=320)
    display_name: str = Field(min_length=1, max_length=200)
    role: Role
    password: str = Field(min_length=12, max_length=200)


class MemberPatch(BaseModel):
    role: Role


class ChannelIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    channel_type: NotificationChannelType
    url: HttpUrl | None = Field(default=None, description="Write-only; required on create")
    signing_secret: str | None = Field(default=None, description="Write-only, webhook channels")
    events: list[str] = Field(default_factory=lambda: ["approval.created"])
    is_active: bool = True


class ChannelOut(ORM):
    id: uuid.UUID
    name: str
    channel_type: NotificationChannelType
    url: SecretFieldState
    signing_secret: SecretFieldState
    events: list[str]
    is_active: bool
    last_delivery_ok: bool | None
    last_delivery_at: datetime | None


class SecretIn(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,200}$")
    value: str = Field(min_length=1, max_length=20_000)
    description: str | None = Field(default=None, max_length=500)


class SecretOut(BaseModel):
    id: uuid.UUID
    ref: str
    name: str
    description: str | None
    hint: str
    version: int
    managed: bool
    updated_at: datetime
