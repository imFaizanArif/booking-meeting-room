from uuid import UUID

from ..errors import ConflictError, NotFoundError
from ..models import Room
from ..repositories.booking_repository import BookingRepository
from ..repositories.room_repository import RoomRepository
from ..schemas import RoomCreateSchema, RoomUpdateSchema


class RoomService:
    def __init__(self) -> None:
        self.rooms = RoomRepository()
        self.bookings = BookingRepository()

    def list_rooms(self, include_inactive: bool = False, search: str | None = None) -> list[dict]:
        return [room.to_dict() for room in self.rooms.list_all(include_inactive, search)]

    def get_room(self, room_id: UUID | str) -> dict:
        room = self._get_or_404(room_id)
        return room.to_dict()

    def create_room(self, payload: dict) -> dict:
        data = RoomCreateSchema(**payload)
        if self.rooms.get_by_name(data.name):
            raise ConflictError(f'A room named "{data.name}" already exists')
        room = self.rooms.create(data.model_dump())
        return room.to_dict()

    def update_room(self, room_id: UUID | str, payload: dict) -> dict:
        room = self._get_or_404(room_id)
        data = RoomUpdateSchema(**payload).model_dump(exclude_unset=True)
        if "name" in data:
            existing = self.rooms.get_by_name(data["name"])
            if existing and str(existing.id) != str(room.id):
                raise ConflictError(f'A room named "{data["name"]}" already exists')
        room = self.rooms.update(room, data)
        return room.to_dict()

    def delete_room(self, room_id: UUID | str) -> None:
        room = self._get_or_404(room_id)
        self.rooms.delete(room)

    def _get_or_404(self, room_id: UUID | str) -> Room:
        room = self.rooms.get_by_id(room_id)
        if room is None:
            raise NotFoundError("Room not found")
        return room
