"""Pydantic request/response validation schemas."""

from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------
class RoomCreateSchema(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    capacity: int = Field(gt=0, le=500)
    floor: int = Field(ge=-5, le=200)
    description: str = Field(default="", max_length=2000)
    image_url: Optional[str] = None
    color: str = Field(default="#2563EB", pattern=r"^#[0-9a-fA-F]{6}$")
    is_active: bool = True


class RoomUpdateSchema(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=80)
    capacity: Optional[int] = Field(default=None, gt=0, le=500)
    floor: Optional[int] = Field(default=None, ge=-5, le=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    image_url: Optional[str] = None
    color: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    is_active: Optional[bool] = None


# ---------------------------------------------------------------------------
# Bookings
# ---------------------------------------------------------------------------
class BookingCreateSchema(BaseModel):
    room_id: UUID
    title: str = Field(min_length=3, max_length=120)
    purpose: str = Field(default="", max_length=2000)
    start_time: datetime
    end_time: datetime
    attendee_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def check_times(self):
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        duration_hours = (self.end_time - self.start_time).total_seconds() / 3600
        if duration_hours > 12:
            raise ValueError("a booking cannot exceed 12 hours")
        return self

    @field_validator("start_time", "end_time")
    @classmethod
    def must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must include a timezone offset (ISO 8601)")
        return value


class BookingUpdateSchema(BaseModel):
    room_id: Optional[UUID] = None
    title: Optional[str] = Field(default=None, min_length=3, max_length=120)
    purpose: Optional[str] = Field(default=None, max_length=2000)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    status: Optional[Literal["pending", "confirmed", "rejected", "cancelled"]] = None
    attendee_ids: Optional[list[UUID]] = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def check_times(self):
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
class UserUpdateSchema(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    department: Optional[str] = Field(default=None, max_length=120)
    designation: Optional[str] = Field(default=None, max_length=120)
    avatar_url: Optional[str] = None
    role: Optional[Literal["employee", "admin"]] = None
    is_active: Optional[bool] = None
