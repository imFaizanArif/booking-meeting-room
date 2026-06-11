from uuid import UUID

from sqlalchemy import or_, select

from ..models import Profile
from .base import BaseRepository


class UserRepository(BaseRepository):
    def list_all(self, search: str | None = None, include_inactive: bool = True) -> list[Profile]:
        stmt = select(Profile).order_by(Profile.name)
        if not include_inactive:
            stmt = stmt.where(Profile.is_active.is_(True))
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Profile.name.ilike(pattern),
                    Profile.email.ilike(pattern),
                    Profile.department.ilike(pattern),
                )
            )
        return list(self.session.scalars(stmt).all())

    def get_by_id(self, user_id: UUID | str) -> Profile | None:
        return self.session.get(Profile, user_id)

    def update(self, user: Profile, data: dict) -> Profile:
        for key, value in data.items():
            setattr(user, key, value)
        self.commit()
        self.session.refresh(user)
        return user
