from __future__ import annotations

import csv
import io
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/debug", tags=["debug"])


@dataclass(frozen=True)
class _Master:
    id: int
    display_name: str
    slug: str
    timezone: str


@dataclass(frozen=True)
class _Service:
    id: int
    master_id: int
    name: str
    price: int
    duration_min: int


def _iter_booking_rows(*, masters: list[_Master], services: list[_Service], count: int, seed: int) -> Iterable[dict[str, str]]:
    rng = random.Random(seed)

    # Simple per-master schedule (UTC): 09:00–18:00, Mon–Sat
    year_start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    year_end = datetime(2026, 12, 31, 23, 59, tzinfo=timezone.utc)

    # Track occupied intervals per master to avoid overlaps in generated data
    occupied: dict[int, list[tuple[datetime, datetime]]] = {m.id: [] for m in masters}

    def overlaps(master_id: int, start: datetime, end: datetime) -> bool:
        for s, e in occupied[master_id]:
            if max(s, start) < min(e, end):
                return True
        return False

    def add_interval(master_id: int, start: datetime, end: datetime) -> None:
        occupied[master_id].append((start, end))

    # Pre-generate some client identities
    client_count = max(80, min(250, count // 2))
    clients = []
    for i in range(1, client_count + 1):
        clients.append(
            {
                "client_id": str(i),
                "client_name": f"Клиент {i}",
                "client_username": f"client{i}",
                "client_phone": f"+7999{rng.randint(1000000, 9999999)}",
            }
        )

    by_master_services: dict[int, list[_Service]] = {}
    for s in services:
        by_master_services.setdefault(s.master_id, []).append(s)

    booking_id = 1
    attempts = 0
    max_attempts = count * 50
    while booking_id <= count and attempts < max_attempts:
        attempts += 1
        master = rng.choice(masters)
        svc = rng.choice(by_master_services[master.id])
        client = rng.choice(clients)

        # Random day in 2026
        delta_days = (year_end.date() - year_start.date()).days
        day = year_start.date() + timedelta(days=rng.randint(0, delta_days))
        # 0=Mon..6=Sun; skip Sunday to make it look more realistic
        if day.weekday() == 6:
            continue

        start_hour = rng.randint(9, 17)
        start_minute = rng.choice([0, 15, 30, 45])
        start = datetime(day.year, day.month, day.day, start_hour, start_minute, tzinfo=timezone.utc)
        end = start + timedelta(minutes=svc.duration_min)
        if end > year_end:
            continue

        if overlaps(master.id, start, end):
            continue
        add_interval(master.id, start, end)

        yield {
            "booking_id": str(booking_id),
            "master_id": str(master.id),
            "master_display_name": master.display_name,
            "master_slug": master.slug,
            "master_timezone": master.timezone,
            "service_id": str(svc.id),
            "service_name": svc.name,
            "service_price": str(svc.price),
            "service_duration_min": str(svc.duration_min),
            "client_id": client["client_id"],
            "client_name": client["client_name"],
            "client_username": client["client_username"],
            "client_phone": client["client_phone"],
            "start_at_utc": start.isoformat(),
            "end_at_utc": end.isoformat(),
            "status": "CONFIRMED",
            "created_at_utc": (start - timedelta(days=rng.randint(0, 30))).isoformat(),
        }
        booking_id += 1


@router.get("/mock_bookings.csv")
def mock_bookings_csv(count: int = 500, masters: int = 10, seed: int = 20260317) -> StreamingResponse:
    """
    Generates a CSV with mock data aligned to current schema (masters/services/clients/bookings).
    Does not write anything to the database.
    """
    if masters < 1 or masters > 50:
        raise ValueError("masters must be 1..50")
    if count < 1 or count > 50_000:
        raise ValueError("count must be 1..50000")

    m_list: list[_Master] = []
    for i in range(1, masters + 1):
        m_list.append(_Master(id=i, display_name=f"Мастер {i}", slug=f"master{i}", timezone="Europe/Moscow"))

    svc_list: list[_Service] = []
    svc_id = 1
    for m in m_list:
        for name, price, dur in [
            ("Маникюр", 2000, 60),
            ("Педикюр", 2500, 60),
            ("Покрытие", 1500, 45),
            ("Снятие", 800, 30),
            ("Дизайн", 600, 15),
        ]:
            svc_list.append(_Service(id=svc_id, master_id=m.id, name=name, price=price, duration_min=dur))
            svc_id += 1

    output = io.StringIO()
    fieldnames = [
        "booking_id",
        "master_id",
        "master_display_name",
        "master_slug",
        "master_timezone",
        "service_id",
        "service_name",
        "service_price",
        "service_duration_min",
        "client_id",
        "client_name",
        "client_username",
        "client_phone",
        "start_at_utc",
        "end_at_utc",
        "status",
        "created_at_utc",
    ]
    w = csv.DictWriter(output, fieldnames=fieldnames)
    w.writeheader()
    for row in _iter_booking_rows(masters=m_list, services=svc_list, count=count, seed=seed):
        w.writerow(row)

    data = output.getvalue().encode("utf-8")
    filename = f"mock_bookings_{count}_2026.csv"
    return StreamingResponse(
        io.BytesIO(data),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )

