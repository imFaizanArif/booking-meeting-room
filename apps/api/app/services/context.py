"""Caller identity passed into every service call."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.enums import ROLE_RANK, Role
from app.core.errors import Forbidden


@dataclass(frozen=True)
class Actor:
    """Who performed an action, for audit. Users, the worker, the scheduler or the system."""

    type: str
    id: str | None = None
    label: str | None = None


SYSTEM_ACTOR = Actor("system", None, "system")
WORKER_ACTOR = Actor("worker", None, "worker")
SCHEDULER_ACTOR = Actor("scheduler", None, "scheduler")


@dataclass(frozen=True)
class AuthContext:
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    role: Role
    email: str
    request_id: str | None = None
    ip: str | None = None

    @property
    def actor(self) -> Actor:
        return Actor("user", str(self.user_id), self.email)

    def require(self, role: Role) -> None:
        if ROLE_RANK[self.role] < ROLE_RANK[role]:
            raise Forbidden(
                f"This action needs the {role.value} role", details={"required_role": role.value}
            )
