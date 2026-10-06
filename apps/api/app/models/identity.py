from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import Role
from app.db.base import Base, IdMixin, TimestampMixin, enum_col


class Workspace(IdMixin, TimestampMixin, Base):
    __tablename__ = "workspaces"

    name: Mapped[str] = mapped_column(sa.String(200))
    slug: Mapped[str] = mapped_column(sa.String(100), unique=True)
    settings: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(sa.String(320), unique=True)
    display_name: Mapped[str] = mapped_column(sa.String(200))
    password_hash: Mapped[str] = mapped_column(sa.String(255))
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    last_login_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))


class WorkspaceMember(IdMixin, TimestampMixin, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (sa.UniqueConstraint("workspace_id", "user_id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[Role] = mapped_column(enum_col(Role, name="role"))


class UserSession(IdMixin, TimestampMixin, Base):
    """Server-side session. Only the SHA-256 of the cookie token is stored."""

    __tablename__ = "user_sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("workspaces.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(sa.String(64))
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(sa.String(64))
    user_agent: Mapped[str | None] = mapped_column(sa.String(400))
