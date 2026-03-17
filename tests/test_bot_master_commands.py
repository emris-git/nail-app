from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone

import pytest

from app.config.settings import get_settings
from app.db import base as db_base
from app.db.models import (
    AvailabilitySlotORM,
    Base,
    BookingORM,
    ClientProfileORM,
    MasterProfileORM,
    ServiceORM,
    UserORM,
)
from app.domain.models import BookingStatus


@dataclass
class FakeFromUser:
    id: int
    full_name: str = "Test User"
    username: str | None = None


class FakeMessage:
    def __init__(self, text: str, user_id: int = 1) -> None:
        self.text = text
        self.from_user = FakeFromUser(id=user_id)
        self.via_bot = None
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs) -> None:  # noqa: ANN001
        self.answers.append(text)


@pytest.fixture(autouse=True)
def _test_settings(monkeypatch: pytest.MonkeyPatch):
    # Изолируем настройки/engine между тестами
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


@pytest.mark.asyncio
async def test_master_enter_name_ignores_commands(db, monkeypatch: pytest.MonkeyPatch):
    # Важно: команда /services не должна обрабатываться как ввод имени мастера
    from app.bot.handlers import start as start_handlers

    # имитируем состояние "ждём имя мастера"
    start_handlers._EXPECT_MASTER_NAME.add(7216100843)

    msg = FakeMessage("/services", user_id=7216100843)
    await start_handlers.master_enter_name(msg)

    # Должны попросить имя, а не запускать онбординг/создавать записи в БД
    assert msg.answers
    assert db.query(UserORM).count() == 0
    assert db.query(MasterProfileORM).count() == 0


@pytest.mark.asyncio
async def test_services_command_shows_list(db):
    from app.bot.handlers import master_services

    # создаём мастера и услуги
    user = UserORM(id=1, username="u", is_master=True)
    db.add(user)
    db.flush()
    master = MasterProfileORM(user_id=user.id, display_name="Мастер", timezone="Europe/Moscow", slug="m1")
    db.add(master)
    db.flush()
    db.add_all(
        [
            ServiceORM(master_id=master.id, name="Маникюр", price=200, duration_minutes=60, is_active=True),
            ServiceORM(master_id=master.id, name="Педикюр", price=180, duration_minutes=60, is_active=True),
        ]
    )
    db.commit()

    msg = FakeMessage("/services", user_id=1)
    await master_services.cmd_services(msg)

    assert msg.answers
    text = msg.answers[-1]
    assert "Маникюр" in text
    assert "Педикюр" in text
    assert "УДАЛИТЬ" in text


@pytest.mark.asyncio
async def test_schedule_marks_booked_slots(db):
    from app.bot.handlers import master_schedule

    # мастер + слоты + 1 запись
    user = UserORM(id=1, username="u", is_master=True)
    db.add(user)
    db.flush()
    master = MasterProfileORM(user_id=user.id, display_name="Мастер", timezone="Europe/Moscow", slug="m1")
    db.add(master)
    db.flush()

    client = ClientProfileORM(tg_user_id=2, name="Клиент", username="c")
    db.add(client)
    db.flush()
    service = ServiceORM(master_id=master.id, name="Маникюр", price=200, duration_minutes=60, is_active=True)
    db.add(service)
    db.flush()

    slot_d = date(2026, 3, 20)
    db.add_all(
        [
            AvailabilitySlotORM(master_id=master.id, slot_date=slot_d, slot_time=time(10, 0)),
            AvailabilitySlotORM(master_id=master.id, slot_date=slot_d, slot_time=time(12, 0)),
        ]
    )

    # booking at 12:00 local MSK == 09:00 UTC (no, MSK is UTC+3 -> 12:00 MSK == 09:00 UTC)
    start_utc = datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc)
    db.add(
        BookingORM(
            master_id=master.id,
            client_id=client.id,
            service_id=service.id,
            start_at=start_utc,
            end_at=start_utc,
            status=BookingStatus.CONFIRMED,
        )
    )
    db.commit()

    msg = FakeMessage("/schedule", user_id=1)
    await master_schedule.cmd_schedule(msg)

    assert msg.answers
    text = msg.answers[-1]
    assert "20/03" in text or "20/03" in text.replace(" ", "")
    assert "10:00" in text
    assert "12:00" in text
    assert "(занято)" in text

