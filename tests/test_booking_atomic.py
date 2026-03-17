from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.config.settings import get_settings
from app.db import base as db_base
from app.db.models import Base, BookingORM, ClientProfileORM, MasterProfileORM, ServiceORM, UserORM
from nail_app_core.services import BookingService, CreateBookingParams, SlotAlreadyBookedError


@pytest.fixture(autouse=True)
def _test_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setenv("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    monkeypatch.setenv("DEFAULT_TIMEZONE", "Europe/Moscow")

    get_settings.cache_clear()
    db_base._engine = None
    db_base._session_factory = None


@pytest.fixture()
def db():
    engine = db_base.get_engine()
    Base.metadata.create_all(engine)
    Session = db_base.get_session_maker()
    s = Session()
    try:
        yield s
    finally:
        s.close()


def test_booking_service_prevents_overlaps(db):
    user = UserORM(id=1, username="u", is_master=True)
    db.add(user)
    db.flush()
    master = MasterProfileORM(user_id=user.id, display_name="M", timezone="Europe/Moscow", slug="m1")
    db.add(master)
    db.flush()
    client = ClientProfileORM(tg_user_id=2, name="C")
    db.add(client)
    db.flush()
    service = ServiceORM(master_id=master.id, name="Маникюр", price=200, duration_minutes=60, is_active=True)
    db.add(service)
    db.flush()

    svc = BookingService(db=db)
    start = datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc)
    end = start + timedelta(minutes=60)

    b1 = svc.create_booking_atomic(
        CreateBookingParams(
            master_id=master.id,
            client_id=client.id,
            service_id=service.id,
            start_at_utc=start,
            end_at_utc=end,
        )
    )
    db.commit()
    assert isinstance(b1, BookingORM)

    with pytest.raises(SlotAlreadyBookedError):
        svc.create_booking_atomic(
            CreateBookingParams(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at_utc=start + timedelta(minutes=30),
                end_at_utc=end + timedelta(minutes=30),
            )
        )

