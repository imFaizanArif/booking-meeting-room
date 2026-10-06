from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class Ok(BaseModel):
    ok: bool = True


class SecretFieldState(BaseModel):
    """Write-only secret as shown by the API: never the value."""

    is_set: bool
    hint: str | None = None
