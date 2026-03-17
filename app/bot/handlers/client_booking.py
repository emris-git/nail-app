from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Dict

from aiogram import Router
from aiogram.types import Message
from zoneinfo import ZoneInfo

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
    master_ids: list[int] | None = None  # для stage choose_master: список id мастеров
    available_slots: list[tuple[date, time]] | None = None  # для stage enter_datetime


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


def _format_slots_for_client(slots: list[tuple[date, time]]) -> str:
    """Группировка по датам: DD/MM  HH:MM, HH:MM."""
    from collections import defaultdict

    by_date: dict[date, list[time]] = defaultdict(list)
    for d, t in slots:
        by_date[d].append(t)
    for d in by_date:
        by_date[d].sort()
    lines = []
    for d in sorted(by_date.keys()):
        times = ", ".join(t.strftime("%H:%M") for t in by_date[d])
        lines.append(f"<b>{d.day:02d}/{d.month:02d}</b>  {times}")
    return "\n".join(lines)


def _parse_client_datetime(text: str) -> tuple[int, int, int, int] | None:
    """Парсит 'ДД/ММ ЧЧ:ММ' или 'ДД.ММ ЧЧ:ММ'."""
    parts = (text or "").strip().split()
    if len(parts) != 2:
        return None
    date_str, time_str = parts
    sep = "/" if "/" in date_str else "."
    try:
        day, month = map(int, date_str.split(sep))
        hour, minute = map(int, time_str.split(":"))
        return day, month, hour, minute
    except ValueError:
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
        text = (message.text or "").strip()
        if text == "/назад":
            if state.stage == "enter_datetime":
                state.stage = "choose_week"
                state.available_slots = None
                set_client_state(user_id, state)
                await message.answer(f"{ru.CLIENT_CHOOSE_WEEK}\n\n{_format_week_options()}")
                return
            if state.stage == "choose_week":
                state.stage = "choose_service"
                state.week_start = None
                state.week_end = None
                state.available_slots = None
                set_client_state(user_id, state)
                services = (
                    db.query(ServiceORM)
                    .filter(ServiceORM.master_id == state.master_id, ServiceORM.is_active.is_(True))
                    .order_by(ServiceORM.id)
                    .all()
                )
                lines = ["Выберите услугу (номер):"]
                for idx, s in enumerate(services, start=1):
                    lines.append(f"{idx}. {s.name} — {int(s.price)}, {s.duration_minutes} мин")
                await message.answer("\n".join(lines))
                return

        if state.stage == "choose_master":
            try:
                index = int((message.text or "").strip()) - 1
            except ValueError:
                await message.answer("Отправьте номер мастера из списка.")
                return
            if not state.master_ids or index < 0 or index >= len(state.master_ids):
                await message.answer("Нет мастера с таким номером. Отправьте /start и выберите клиент.")
                return
            master_id = state.master_ids[index]
            master = db.get(MasterProfileORM, master_id)
            if master is None:
                await message.answer("Мастер не найден. Отправьте /start.")
                clear_client_state(user_id)
                return
            services = (
                db.query(ServiceORM)
                .filter(ServiceORM.master_id == master_id, ServiceORM.is_active.is_(True))
                .order_by(ServiceORM.id)
                .all()
            )
            if not services:
                await message.answer("У этого мастера пока нет услуг для записи.")
                return
            state.master_id = master_id
            state.stage = "choose_service"
            state.master_ids = None
            set_client_state(user_id, state)
            lines = [f"Запись к мастеру {master.display_name}", "", "Выберите услугу (номер):"]
            for idx, s in enumerate(services, start=1):
                lines.append(f"{idx}. {s.name} — {int(s.price)}, {s.duration_minutes} мин")
            await message.answer("\n".join(lines))
            return

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
            # Слоты в выбранной неделе (с учётом записей) показываем сразу
            master = db.get(MasterProfileORM, state.master_id)
            if master is None:
                await message.answer("Мастер не найден. Начните заново.")
                clear_client_state(user_id)
                return
            tz = ZoneInfo(master.timezone)
            now_local = datetime.now(tz)

            all_slots = (
                db.query(AvailabilitySlotORM)
                .filter(AvailabilitySlotORM.master_id == state.master_id)
                .filter(AvailabilitySlotORM.slot_date >= state.week_start)
                .filter(AvailabilitySlotORM.slot_date <= state.week_end)
                .order_by(AvailabilitySlotORM.slot_date, AvailabilitySlotORM.slot_time)
                .all()
            )
            bookings = (
                db.query(BookingORM)
                .filter(BookingORM.master_id == state.master_id)
                .all()
            )
            booked_set: set[tuple[date, time]] = set()
            for b in bookings:
                local = b.start_at.astimezone(tz)
                booked_set.add((local.date(), time(local.hour, local.minute)))

            available: list[tuple[date, time]] = []
            for s in all_slots:
                if (s.slot_date, s.slot_time) in booked_set:
                    continue
                # не показываем прошедшее время
                dt_local = datetime(
                    s.slot_date.year, s.slot_date.month, s.slot_date.day, s.slot_time.hour, s.slot_time.minute, tzinfo=tz
                )
                if dt_local < now_local:
                    continue
                available.append((s.slot_date, s.slot_time))

            if not available:
                state.available_slots = []
                set_client_state(user_id, state)
                await message.answer(ru.CLIENT_NO_SLOTS_WEEK)
                return

            state.available_slots = available
            set_client_state(user_id, state)
            await message.answer(
                "Доступные слоты на выбранной неделе:\n\n"
                + _format_slots_for_client(available)
                + "\n\n"
                + ru.CLIENT_ENTER_DATETIME
            )
            return

        if state.stage == "enter_datetime":
            # Можно выбрать номер слота
            if (message.text or "").strip().isdigit() and state.available_slots:
                idx = int((message.text or "").strip()) - 1
                if 0 <= idx < len(state.available_slots):
                    chosen_date, chosen_time = state.available_slots[idx]
                    day, month, hour, minute = (
                        chosen_date.day,
                        chosen_date.month,
                        chosen_time.hour,
                        chosen_time.minute,
                    )
                else:
                    await message.answer("Нет слота с таким номером. Попробуйте ещё раз.")
                    return
            else:
                parsed_dt = _parse_client_datetime(message.text or "")
                if parsed_dt is None:
                    await message.answer("Формат: ДД/ММ ЧЧ:ММ. Например: 25/03 14:00")
                    return
                day, month, hour, minute = parsed_dt

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
                        state.week_start.strftime("%d/%m"),
                        state.week_end.strftime("%d/%m"),
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
                start_at=start_local.astimezone(timezone.utc),
                end_at=end_local.astimezone(timezone.utc),
                status="CONFIRMED",
            )
            db.add(booking)
            db.commit()

            await message.answer(
                "Запись создана!\n\n"
                f"Мастер: {master.display_name}\n"
                f"Услуга: {service.name}\n"
                f"Дата и время: {start_local.strftime('%d/%m %H:%M')}\n\n"
                f"{ru.CLIENT_ANOTHER_BOOKING}"
            )
            state.stage = "another_booking"
            state.chosen_service_id = None
            state.week_start = None
            state.week_end = None
            state.available_slots = None
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

