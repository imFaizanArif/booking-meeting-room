"""Base repository providing a shared SQLAlchemy session."""

from sqlalchemy.orm import Session

from ..extensions import get_session_factory


class BaseRepository:
    @property
    def session(self) -> Session:
        return get_session_factory()()

    def commit(self) -> None:
        try:
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
