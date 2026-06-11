"""SQLAlchemy ORM models mapping the Supabase PostgreSQL schema."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

user_role_enum = ENUM("employee", "admin", name="user_role", create_type=False)
booking_status_enum = ENUM(
    "pending", "confirmed", "rejected", "cancelled",
    name="booking_status", create_type=False,
)


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    department: Mapped[str] = mapped_column(Text, nullable=False, default="")
    designation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(user_role_enum, nullable=False, default="employee")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    bookings: Mapped[list["Booking"]] = relationship(back_populates="user")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "email": self.email,
            "department": self.department,
            "designation": self.designation,
            "avatar_url": self.avatar_url,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(Text, nullable=False, default="#2563EB")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    bookings: Mapped[list["Booking"]] = relationship(back_populates="room")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "capacity": self.capacity,
            "floor": self.floor,
            "description": self.description,
            "image_url": self.image_url,
            "color": self.color,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(
        booking_status_enum, nullable=False, default="confirmed"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    room: Mapped["Room"] = relationship(back_populates="bookings")
    user: Mapped["Profile"] = relationship(back_populates="bookings")
    attendees: Mapped[list["Attendee"]] = relationship(
        back_populates="booking", cascade="all, delete-orphan"
    )

    def to_dict(self, include_relations: bool = True) -> dict:
        data = {
            "id": str(self.id),
            "room_id": str(self.room_id),
            "user_id": str(self.user_id),
            "title": self.title,
            "purpose": self.purpose,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_relations:
            data["room"] = self.room.to_dict() if self.room else None
            data["user"] = self.user.to_dict() if self.user else None
            data["attendees"] = [a.to_dict() for a in self.attendees]
        return data


class Attendee(Base):
    __tablename__ = "attendees"
    __table_args__ = (UniqueConstraint("booking_id", "user_id", name="attendees_unique"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bookings.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )

    booking: Mapped["Booking"] = relationship(back_populates="attendees")
    user: Mapped["Profile"] = relationship()

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "booking_id": str(self.booking_id),
            "user_id": str(self.user_id),
            "user": self.user.to_dict() if self.user else None,
        }
