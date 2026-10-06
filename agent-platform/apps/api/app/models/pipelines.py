from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import OverlapPolicy, ScheduleKind
from app.db.base import Base, IdMixin, TimestampMixin, WorkspaceScoped, enum_col


class Pipeline(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "pipelines"
    __table_args__ = (sa.UniqueConstraint("workspace_id", "slug"),)

    name: Mapped[str] = mapped_column(sa.String(200))
    slug: Mapped[str] = mapped_column(sa.String(100))
    description: Mapped[str | None] = mapped_column(sa.Text)
    latest_version_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("pipeline_versions.id", use_alter=True, ondelete="SET NULL")
    )
    latest_version_number: Mapped[int] = mapped_column(default=0)
    is_archived: Mapped[bool] = mapped_column(default=False)
    webhook_secret_ref: Mapped[str | None] = mapped_column(sa.String(80))


class PipelineVersion(IdMixin, TimestampMixin, Base):
    """Immutable. A new save always creates a new version row."""

    __tablename__ = "pipeline_versions"
    __table_args__ = (sa.UniqueConstraint("pipeline_id", "version"),)

    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("pipelines.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    graph: Mapped[dict[str, Any]]
    graph_hash: Mapped[str] = mapped_column(sa.String(64))
    change_note: Mapped[str | None] = mapped_column(sa.String(500))
    created_by: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))


class Schedule(IdMixin, TimestampMixin, WorkspaceScoped, Base):
    __tablename__ = "schedules"

    pipeline_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("pipelines.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(sa.String(200))
    kind: Mapped[ScheduleKind] = mapped_column(enum_col(ScheduleKind, name="schedule_kind"))
    cron: Mapped[str | None] = mapped_column(sa.String(120))
    interval_seconds: Mapped[int | None]
    daily_time: Mapped[str | None] = mapped_column(sa.String(5), comment="HH:MM")
    timezone: Mapped[str] = mapped_column(sa.String(64), default="UTC")
    input: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    overlap_policy: Mapped[OverlapPolicy] = mapped_column(
        enum_col(OverlapPolicy, name="overlap_policy"), default=OverlapPolicy.skip
    )
    is_active: Mapped[bool] = mapped_column(default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), index=True)


class ScheduleFire(IdMixin, TimestampMixin, Base):
    """One row per occurrence. The unique key makes a fire happen exactly once."""

    __tablename__ = "schedule_fires"
    __table_args__ = (sa.UniqueConstraint("schedule_id", "fire_at"),)

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("schedules.id", ondelete="CASCADE"), index=True
    )
    fire_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("executions.id", ondelete="SET NULL")
    )
    outcome: Mapped[str] = mapped_column(sa.String(40), comment="enqueued | skipped_overlap | failed")
    fired_by: Mapped[str] = mapped_column(sa.String(120))
