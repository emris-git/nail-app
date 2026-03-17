from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Dict

from aiogram import Router
from aiogram.types import Message

from app.bot.texts import ru
from app.adapters.time_utils import make_timezone
from app.config import get_settings
from app.db.base import get_session_maker
from app.db.models import (
    AvailabilitySlotORM,
    BookingORM,
    ClientProfileORM,
    MasterProfileORM,
    ServiceORM,
)

router = Router()


def _current_week_range() -> tuple[date, date]:
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    return monday, sunday


def _next_week_range() -> tuple[date, date]:
    m1, s1 = _current_week_range()
    delta = timedelta(days=7)
    return m1 + delta, s1 + delta


@dataclass
class ClientState:
    master_id: int
    stage: str
    chosen_service_id: int | None = None
    week_start: date | None = None
    week_end: date | None = None


_CLIENT_STATES: Dict[int, ClientState] = {}


def set_client_state(user_id: int, state: ClientState) -> None:
    _CLIENT_STATES[user_id] = state


def get_client_state(user_id: int) -> ClientState | None:
    return _CLIENT_STATES.get(user_id)


def clear_client_state(user_id: int) -> None:
    _CLIENT_STATES.pop(user_id, None)


def _in_client_flow(message: Message) -> bool:
    return get_client_state(message.from_user.id) is not None


def _format_week_options() -> str:
    cur_start, cur_end = _current_week_range()
    next_start, next_end = _next_week_range()
    return (
        f"1. Текущая неделя: {cur_start.strftime('%d.%m')}–{cur_end.strftime('%d.%m')}\n"
        f"2. Следующая неделя: {next_start.strftime('%d.%m')}–{next_end.strftime('%d.%m')}"
    )


def _parse_week_input(text: str) -> tuple[date, date] | None:
    """Парсит '1', '2' или 'ДД.ММ–ДД.ММ' / 'ДД.ММ ДД.ММ'. Возвращает (week_start, week_end) или None."""
    text = text.strip()
    if text == "1":
        return _current_week_range()
    if text == "2":
        return _next_week_range()
    parts = None
    if "–" in text:
        parts = text.split("–", 1)
    elif "-" in text:
        parts = text.split("-", 1)
    elif " " in text:
        parts = text.split(None, 1)
    if not parts or len(parts) != 2:
        return None
    a, b = parts[0].strip(), parts[1].strip()
    try:
        d1, m1 = map(int, a.split("."))
        d2, m2 = map(int, b.split("."))
    except ValueError:
        return None
    y = date.today().year
    try:
        start = date(y, m1, d1)
        end = date(y, m2, d2)
        if start <= end:
            return start, end
    except ValueError:
        pass
    return None


@router.message(_in_client_flow)
async def handle_client_flow(message: Message) -> None:
    user_id = message.from_user.id
    state = get_client_state(user_id)
    if state is None:
        return

    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        if state.stage == "choose_service":
            try:
                index = int(message.text.strip()) - 1
            except ValueError:
                await message.answer("Пожалуйста, отправьте номер услуги из списка.")
                return

            services = (
                db.query(ServiceORM)
                .filter(ServiceORM.master_id == state.master_id, ServiceORM.is_active.is_(True))
                .order_by(ServiceORM.id)
                .all()
            )
            if index < 0 or index >= len(services):
                await message.answer("Нет услуги с таким номером. Попробуйте ещё раз.")
                return

            service = services[index]
            state.chosen_service_id = service.id
            state.stage = "choose_week"
            state.week_start = None
            state.week_end = None
            set_client_state(user_id, state)

            await message.answer(
                "Вы выбрали услугу:\n"
                f"{service.name} — {int(service.price)} ₽, {service.duration_minutes} мин.\n\n"
                f"{ru.CLIENT_CHOOSE_WEEK}\n\n"
                f"{_format_week_options()}"
            )
            return

        if state.stage == "choose_week":
            week_range = _parse_week_input(message.text or "")
            if week_range is None:
                await message.answer(
                    "Укажите номер (1 или 2) или диапазон дат, например: 24.03–30.03"
                )
                return
            state.week_start, state.week_end = week_range
            state.stage = "enter_datetime"
            set_client_state(user_id, state)
            await message.answer(ru.CLIENT_ENTER_DATETIME)
            return

        if state.stage == "enter_datetime":
            parts = (message.text or "").strip().split()
            if len(parts) != 2:
                await message.answer("Нужны дата и время, например: 25.03 14:00")
                return
            date_str, time_str = parts
            try:
                day, month = map(int, date_str.split("."))
                hour, minute = map(int, time_str.split(":"))
            except ValueError:
                await message.answer("Формат: ДД.ММ и ЧЧ:ММ. Например: 25.03 14:00")
                return

            if state.week_start is None or state.week_end is None:
                await message.answer("Ошибка: не выбрана неделя. Начните запись заново.")
                clear_client_state(user_id)
                return

            chosen_date = date(state.week_start.year, month, day)
            if chosen_date < state.week_start or chosen_date > state.week_end:
                chosen_date = date(state.week_end.year, month, day)
            if chosen_date < state.week_start or chosen_date > state.week_end:
                await message.answer(
                    ru.CLIENT_DATE_NOT_IN_WEEK.format(
                        state.week_start.strftime("%d.%m"),
                        state.week_end.strftime("%d.%m"),
                    )
                )
                return

            local_tz = make_timezone(get_settings().default_timezone)
            start_local = datetime(
                year=chosen_date.year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                tzinfo=local_tz,
            )

            service = db.get(ServiceORM, state.chosen_service_id)
            master = db.get(MasterProfileORM, state.master_id)
            if service is None or master is None:
                await message.answer("Ошибка при создании записи. Попробуйте позже.")
                clear_client_state(user_id)
                return

            # Если у мастера настроены слоты — проверяем, что выбранное время есть в расписании
            chosen_time = time(hour, minute)
            slots_count = (
                db.query(AvailabilitySlotORM)
                .filter(AvailabilitySlotORM.master_id == state.master_id)
                .count()
            )
            if slots_count > 0:
                slot_exists = (
                    db.query(AvailabilitySlotORM)
                    .filter(
                        AvailabilitySlotORM.master_id == state.master_id,
                        AvailabilitySlotORM.slot_date == chosen_date,
                        AvailabilitySlotORM.slot_time == chosen_time,
                    )
                    .first()
                )
                if not slot_exists:
                    await message.answer(ru.CLIENT_SLOT_NOT_AVAILABLE)
                    return

            end_local = start_local + timedelta(minutes=service.duration_minutes)

            client = (
                db.query(ClientProfileORM)
                .filter(ClientProfileORM.tg_user_id == user_id)
                .one_or_none()
            )
            if client is None:
                client = ClientProfileORM(
                    tg_user_id=user_id,
                    name=message.from_user.full_name or "Клиент",
                    username=message.from_user.username,
                )
                db.add(client)
                db.flush()

            booking = BookingORM(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at=start_local.astimezone(datetime.timezone.utc),
                end_at=end_local.astimezone(datetime.timezone.utc),
                status="CONFIRMED",
            )
            db.add(booking)
            db.commit()

            await message.answer(
                "Запись создана!\n\n"
                f"Мастер: {master.display_name}\n"
                f"Услуга: {service.name}\n"
                f"Дата и время: {start_local.strftime('%d.%m %H:%M')}\n\n"
                f"{ru.CLIENT_ANOTHER_BOOKING}"
            )
            state.stage = "another_booking"
            state.chosen_service_id = None
            state.week_start = None
            state.week_end = None
            set_client_state(user_id, state)
            return

        if state.stage == "another_booking":
            answer = (message.text or "").strip().lower()
            if answer in ("да", "давай", "yes", "д"):
                state.stage = "choose_service"
                set_client_state(user_id, state)
                services = (
                    db.query(ServiceORM)
                    .filter(ServiceORM.master_id == state.master_id, ServiceORM.is_active.is_(True))
                    .order_by(ServiceORM.id)
                    .all()
                )
                lines = ["Выберите услугу (номер):"]
                for idx, s in enumerate(services, start=1):
                    lines.append(f"{idx}. {s.name} — {int(s.price)} ₽, {s.duration_minutes} мин")
                await message.answer("\n".join(lines))
                return
            if answer in ("нет", "нет.", "no", "н"):
                await message.answer(ru.CLIENT_BOOKING_DONE)
                clear_client_state(user_id)
                return
            await message.answer("Напишите <b>да</b> или <b>нет</b>.")
    finally:
        db.close()

