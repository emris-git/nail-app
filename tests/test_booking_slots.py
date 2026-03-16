from datetime import date, datetime, time, timezone, timedelta

from app.domain.booking_rules import Slot, generate_slots_for_service
from app.domain.models import Booking, BookingStatus, Service, WorkingWindow


def make_booking(start: datetime, end: datetime) -> Booking:
    return Booking(
        id=1,
        master_id=1,
        client_id=1,
        service_id=1,
        start_at=start,
        end_at=end,
        status=BookingStatus.CONFIRMED,
        created_at=start,
    )


def test_generate_slots_simple():
    tz = timezone.utc
    today = date(2024, 1, 1)
    service = Service(id=1, master_id=1, name="Маникюр", price=1000, duration_minutes=60)
    window = WorkingWindow(
        id=1,
        master_id=1,
        weekday=today.weekday(),
        start_time=time(10, 0),
        end_time=time(12, 0),
    )
    existing = []

    slots = generate_slots_for_service(
        target_date=today,
        service=service,
        working_windows=[window],
        existing_bookings=existing,
        tz=tz,
    )

    assert len(slots) == 2
    assert slots[0].start_at.hour == 10
    assert slots[1].start_at.hour == 11


def test_generate_slots_skips_overlaps():
    tz = timezone.utc
    today = date(2024, 1, 1)
    service = Service(id=1, master_id=1, name="Маникюр", price=1000, duration_minutes=60)
    window = WorkingWindow(
        id=1,
        master_id=1,
        weekday=today.weekday(),
        start_time=time(10, 0),
        end_time=time(13, 0),
    )

    start_existing = datetime(2024, 1, 1, 11, 0, tzinfo=tz)
    existing = [make_booking(start_existing, start_existing + timedelta(hours=1))]

    slots = generate_slots_for_service(
        target_date=today,
        service=service,
        working_windows=[window],
        existing_bookings=existing,
        tz=tz,
    )

    hours = [s.start_at.hour for s in slots]
    assert hours == [10, 12]

