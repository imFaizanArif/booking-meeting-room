from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Schema(BaseModel):
    """Base for API DTOs. Response schemas list defaulted fields as required (they are always
    present), so generated TypeScript types are exact; request schemas keep them optional."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class ORM(Schema):
    model_config = ConfigDict(from_attributes=True, json_schema_serialization_defaults_required=True)


class Page(Schema, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Ok(Schema):
    ok: bool = True


class SecretFieldState(Schema):
    """Write-only secret as shown by the API: never the value."""

    is_set: bool
    hint: str | None = None
