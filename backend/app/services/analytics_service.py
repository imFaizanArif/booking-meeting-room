from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from ..models import Booking, Profile, Room
from ..repositories.base import BaseRepository

WORKDAY_HOURS = 10  # 8:00 – 18:00 considered bookable for utilization math


class AnalyticsService(BaseRepository):
    def get_dashboard_stats(self) -> dict:
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        week_ahead = now + timedelta(days=7)

        total_bookings = self.session.scalar(select(func.count(Booking.id))) or 0
        active_rooms = self.session.scalar(
            select(func.count(Room.id)).where(Room.is_active.is_(True))
        ) or 0
        total_users = self.session.scalar(
            select(func.count(Profile.id)).where(Profile.is_active.is_(True))
        ) or 0
        upcoming = self.session.scalar(
            select(func.count(Booking.id)).where(
                Booking.start_time >= now,
                Booking.start_time <= week_ahead,
                Booking.status.in_(("pending", "confirmed")),
            )
        ) or 0
        pending = self.session.scalar(
            select(func.count(Booking.id)).where(Booking.status == "pending")
        ) or 0

        # Per-room utilization over the past 7 days
        rows = self.session.execute(
            select(
                Room.id,
                Room.name,
                Room.color,
                func.coalesce(
                    func.sum(
                        func.extract("epoch", Booking.end_time - Booking.start_time)
                    ),
                    0,
                ),
                func.count(Booking.id),
            )
            .outerjoin(
                Booking,
                (Booking.room_id == Room.id)
                & (Booking.start_time >= week_ago)
                & (Booking.start_time <= now)
                & (Booking.status.in_(("pending", "confirmed"))),
            )
            .where(Room.is_active.is_(True))
            .group_by(Room.id, Room.name, Room.color)
            .order_by(Room.name)
        ).all()

        bookable_seconds = 7 * WORKDAY_HOURS * 3600
        utilization = [
            {
                "room_id": str(room_id),
                "room_name": name,
                "color": color,
                "booked_hours": round(float(seconds) / 3600, 1),
                "bookings_count": count,
                "utilization_pct": min(round(float(seconds) / bookable_seconds * 100, 1), 100.0),
            }
            for room_id, name, color, seconds, count in rows
        ]

        # Bookings per day for the past 7 days (trend chart)
        per_day_rows = self.session.execute(
            select(
                func.date_trunc("day", Booking.start_time).label("day"),
                func.count(Booking.id),
            )
            .where(Booking.start_time >= week_ago, Booking.start_time <= week_ahead)
            .group_by("day")
            .order_by("day")
        ).all()

        return {
            "total_bookings": total_bookings,
            "active_rooms": active_rooms,
            "total_users": total_users,
            "upcoming_meetings": upcoming,
            "pending_approvals": pending,
            "room_utilization": utilization,
            "bookings_per_day": [
                {"date": day.date().isoformat(), "count": count}
                for day, count in per_day_rows
            ],
        }
