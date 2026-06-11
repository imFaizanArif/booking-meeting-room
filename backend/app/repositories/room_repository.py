from uuid import UUID

from sqlalchemy import select

from ..models import Room
from .base import BaseRepository


class RoomRepository(BaseRepository):
    def list_all(self, include_inactive: bool = False, search: str | None = None) -> list[Room]:
        stmt = select(Room).order_by(Room.floor, Room.name)
        if not include_inactive:
            stmt = stmt.where(Room.is_active.is_(True))
        if search:
            stmt = stmt.where(Room.name.ilike(f"%{search}%"))
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, room_id: UUID | str) -> Room | None:
        return self.session.get(Room, room_id)

    def get_by_name(self, name: str) -> Room | None:
        return self.session.scalar(select(Room).where(Room.name == name))

    def create(self, data: dict) -> Room:
        room = Room(**data)
        self.session.add(room)
        self.commit()
        self.session.refresh(room)
        return room

    def update(self, room: Room, data: dict) -> Room:
        for key, value in data.items():
            setattr(room, key, value)
        self.commit()
        self.session.refresh(room)
        return room

    def delete(self, room: Room) -> None:
        self.session.delete(room)
        self.commit()
