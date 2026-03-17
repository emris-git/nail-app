from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from nail_app_core.db.models import BookingORM


class SlotAlreadyBookedError(RuntimeError):
    pass


@dataclass(frozen=True)
class CreateBookingParams:
    master_id: int
    client_id: int
    service_id: int
    start_at_utc: datetime
    end_at_utc: datetime


class BookingService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create_booking_atomic(self, params: CreateBookingParams) -> BookingORM:
        if params.start_at_utc.tzinfo is None:
            raise ValueError("start_at_utc must be timezone-aware")
        if params.end_at_utc.tzinfo is None:
            raise ValueError("end_at_utc must be timezone-aware")

        start_utc = params.start_at_utc.astimezone(timezone.utc)
        end_utc = params.end_at_utc.astimezone(timezone.utc)

        overlap_stmt = (
            select(BookingORM.id)
            .where(BookingORM.master_id == params.master_id)
            .where(BookingORM.status == "CONFIRMED")
            .where(and_(BookingORM.start_at < end_utc, BookingORM.end_at > start_utc))
            .limit(1)
            .with_for_update()
        )
        overlap = self._db.execute(overlap_stmt).scalar_one_or_none()
        if overlap is not None:
            raise SlotAlreadyBookedError("Slot overlaps an existing booking")

        booking = BookingORM(
            master_id=params.master_id,
            client_id=params.client_id,
            service_id=params.service_id,
            start_at=start_utc,
            end_at=end_utc,
            status="CONFIRMED",
        )
        self._db.add(booking)
        self._db.flush()
        return booking

