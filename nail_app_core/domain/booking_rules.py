from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable, List, Sequence

from .models import Booking, Service, WorkingWindow


@dataclass(frozen=True)
class Slot:
    start_at: datetime
    end_at: datetime


def _overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return max(start_a, start_b) < min(end_a, end_b)


def generate_slots_for_service(
    *,
    target_date: date,
    service: Service,
    working_windows: Sequence[WorkingWindow],
    existing_bookings: Iterable[Booking],
    tz: timezone,
) -> List[Slot]:
    day_start = datetime.combine(target_date, time(0, 0)).replace(tzinfo=tz)
    bookings = list(existing_bookings)
    slots: list[Slot] = []

    for window in working_windows:
        window_start = day_start.replace(
            hour=window.start_time.hour,
            minute=window.start_time.minute,
            second=0,
            microsecond=0,
        )
        window_end = day_start.replace(
            hour=window.end_time.hour,
            minute=window.end_time.minute,
            second=0,
            microsecond=0,
        )

        step = timedelta(minutes=service.duration_minutes)
        current_start = window_start

        while current_start + step <= window_end:
            current_end = current_start + step
            if not any(
                _overlaps(current_start, current_end, b.start_at, b.end_at)
                for b in bookings
                if b.status == "CONFIRMED"
            ):
                slots.append(Slot(start_at=current_start, end_at=current_end))
            current_start = current_start + step

    return slots

