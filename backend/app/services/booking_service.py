from datetime import datetime
from uuid import UUID

from ..errors import ConflictError, ForbiddenError, NotFoundError
from ..models import Booking, Profile
from ..repositories.booking_repository import BookingRepository
from ..repositories.room_repository import RoomRepository
from ..repositories.user_repository import UserRepository
from ..schemas import BookingCreateSchema, BookingUpdateSchema


class BookingService:
    def __init__(self) -> None:
        self.bookings = BookingRepository()
        self.rooms = RoomRepository()
        self.users = UserRepository()

    # ------------------------------------------------------------------ reads
    def list_bookings(
        self,
        room_id: str | None = None,
        user_id: str | None = None,
        status: str | None = None,
        start_after: str | None = None,
        end_before: str | None = None,
        search: str | None = None,
    ) -> list[dict]:
        results = self.bookings.list_filtered(
            room_id=UUID(room_id) if room_id else None,
            user_id=UUID(user_id) if user_id else None,
            status=status,
            start_after=datetime.fromisoformat(start_after) if start_after else None,
            end_before=datetime.fromisoformat(end_before) if end_before else None,
            search=search,
        )
        return [b.to_dict() for b in results]

    def get_booking(self, booking_id: str) -> dict:
        return self._get_or_404(booking_id).to_dict()

    # ----------------------------------------------------------------- writes
    def create_booking(self, payload: dict, current_user: Profile) -> dict:
        data = BookingCreateSchema(**payload)

        room = self.rooms.get_by_id(data.room_id)
        if room is None or not room.is_active:
            raise NotFoundError("Room not found or inactive")

        self._validate_attendees(data.attendee_ids)
        self._assert_no_conflict(data.room_id, data.start_time, data.end_time)

        booking = self.bookings.create(
            {
                "room_id": data.room_id,
                "user_id": current_user.id,
                "title": data.title,
                "purpose": data.purpose,
                "start_time": data.start_time,
                "end_time": data.end_time,
                "status": "confirmed",
            },
            attendee_ids=data.attendee_ids,
        )
        return booking.to_dict()

    def update_booking(self, booking_id: str, payload: dict, current_user: Profile) -> dict:
        booking = self._get_or_404(booking_id)
        self._assert_can_modify(booking, current_user)

        data = BookingUpdateSchema(**payload)
        updates = data.model_dump(exclude_unset=True, exclude={"attendee_ids"})

        # Only admins may change status to approved/rejected; owners may cancel.
        if "status" in updates and current_user.role != "admin":
            if updates["status"] != "cancelled":
                raise ForbiddenError("Only admins can approve or reject bookings")

        new_room_id = updates.get("room_id", booking.room_id)
        new_start = updates.get("start_time", booking.start_time)
        new_end = updates.get("end_time", booking.end_time)
        new_status = updates.get("status", booking.status)

        if new_end <= new_start:
            raise ConflictError("end_time must be after start_time")

        if new_status in ("pending", "confirmed"):
            self._assert_no_conflict(new_room_id, new_start, new_end, exclude=booking.id)

        if data.attendee_ids is not None:
            self._validate_attendees(data.attendee_ids)

        booking = self.bookings.update(booking, updates, data.attendee_ids)
        return booking.to_dict()

    def cancel_booking(self, booking_id: str, current_user: Profile) -> dict:
        booking = self._get_or_404(booking_id)
        self._assert_can_modify(booking, current_user)
        booking = self.bookings.update(booking, {"status": "cancelled"}, None)
        return booking.to_dict()

    def delete_booking(self, booking_id: str, current_user: Profile) -> None:
        booking = self._get_or_404(booking_id)
        self._assert_can_modify(booking, current_user)
        self.bookings.delete(booking)

    def check_availability(self, room_id: str, start_time: str, end_time: str) -> dict:
        conflicts = self.bookings.find_conflicts(
            UUID(room_id),
            datetime.fromisoformat(start_time),
            datetime.fromisoformat(end_time),
        )
        return {
            "available": len(conflicts) == 0,
            "conflicts": [c.to_dict(include_relations=False) for c in conflicts],
        }

    # ---------------------------------------------------------------- helpers
    def _get_or_404(self, booking_id: str) -> Booking:
        booking = self.bookings.get_by_id(booking_id)
        if booking is None:
            raise NotFoundError("Booking not found")
        return booking

    def _assert_can_modify(self, booking: Booking, user: Profile) -> None:
        if str(booking.user_id) != str(user.id) and user.role != "admin":
            raise ForbiddenError("You can only modify your own bookings")

    def _assert_no_conflict(
        self, room_id: UUID, start: datetime, end: datetime, exclude: UUID | None = None
    ) -> None:
        conflicts = self.bookings.find_conflicts(room_id, start, end, exclude_booking_id=exclude)
        if conflicts:
            first = conflicts[0]
            raise ConflictError(
                f'This slot overlaps with "{first.title}" '
                f"({first.start_time:%H:%M}–{first.end_time:%H:%M}). "
                "Please pick another time."
            )

    def _validate_attendees(self, attendee_ids: list[UUID]) -> None:
        for uid in attendee_ids:
            user = self.users.get_by_id(uid)
            if user is None or not user.is_active:
                raise NotFoundError(f"Attendee {uid} not found or inactive")
