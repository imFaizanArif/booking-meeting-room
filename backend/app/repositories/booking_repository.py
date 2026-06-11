from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import joinedload

from ..models import Attendee, Booking
from .base import BaseRepository

ACTIVE_STATUSES = ("pending", "confirmed")


class BookingRepository(BaseRepository):
    def _base_query(self):
        return select(Booking).options(
            joinedload(Booking.room),
            joinedload(Booking.user),
            joinedload(Booking.attendees).joinedload(Attendee.user),
        )

    def list_filtered(
        self,
        room_id: UUID | None = None,
        user_id: UUID | None = None,
        status: str | None = None,
        start_after: datetime | None = None,
        end_before: datetime | None = None,
        search: str | None = None,
    ) -> list[Booking]:
        stmt = self._base_query().order_by(Booking.start_time)
        if room_id:
            stmt = stmt.where(Booking.room_id == room_id)
        if user_id:
            stmt = stmt.where(
                or_(
                    Booking.user_id == user_id,
                    Booking.id.in_(
                        select(Attendee.booking_id).where(Attendee.user_id == user_id)
                    ),
                )
            )
        if status:
            stmt = stmt.where(Booking.status == status)
        if start_after:
            stmt = stmt.where(Booking.end_time >= start_after)
        if end_before:
            stmt = stmt.where(Booking.start_time <= end_before)
        if search:
            stmt = stmt.where(Booking.title.ilike(f"%{search}%"))
        return list(self.session.scalars(stmt).unique().all())

    def get_by_id(self, booking_id: UUID | str) -> Booking | None:
        stmt = self._base_query().where(Booking.id == booking_id)
        return self.session.scalars(stmt).unique().one_or_none()

    def find_conflicts(
        self,
        room_id: UUID,
        start_time: datetime,
        end_time: datetime,
        exclude_booking_id: UUID | None = None,
    ) -> list[Booking]:
        """Active bookings of the same room overlapping [start_time, end_time)."""
        stmt = self._base_query().where(
            and_(
                Booking.room_id == room_id,
                Booking.status.in_(ACTIVE_STATUSES),
                Booking.start_time < end_time,
                Booking.end_time > start_time,
            )
        )
        if exclude_booking_id:
            stmt = stmt.where(Booking.id != exclude_booking_id)
        return list(self.session.scalars(stmt).unique().all())

    def create(self, data: dict, attendee_ids: list[UUID]) -> Booking:
        booking = Booking(**data)
        self.session.add(booking)
        self.session.flush()
        for uid in set(attendee_ids):
            self.session.add(Attendee(booking_id=booking.id, user_id=uid))
        self.commit()
        return self.get_by_id(booking.id)

    def update(self, booking: Booking, data: dict, attendee_ids: list[UUID] | None) -> Booking:
        for key, value in data.items():
            setattr(booking, key, value)
        if attendee_ids is not None:
            for attendee in list(booking.attendees):
                self.session.delete(attendee)
            self.session.flush()
            for uid in set(attendee_ids):
                self.session.add(Attendee(booking_id=booking.id, user_id=uid))
        self.commit()
        return self.get_by_id(booking.id)

    def delete(self, booking: Booking) -> None:
        self.session.delete(booking)
        self.commit()
