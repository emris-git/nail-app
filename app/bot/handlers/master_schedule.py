from __future__ import annotations

from collections import defaultdict
from datetime import date, time

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from zoneinfo import ZoneInfo

from app.bot.parsers import parse_schedule_lines
from app.db.base import get_session_maker
from app.db.models import AvailabilitySlotORM, BookingORM, MasterProfileORM

router = Router()


def _format_schedule_with_bookings(
    slots: list[tuple[date, time]],
    booked_set: set[tuple[date, time]],
) -> str:
    """Слоты по датам; занятые помечаем (занято)."""
    by_date: dict[date, list[tuple[time, bool]]] = defaultdict(list)
    for slot_date, slot_time in slots:
        by_date[slot_date].append((slot_time, (slot_date, slot_time) in booked_set))
    for d in by_date:
        by_date[d].sort(key=lambda x: x[0])
    lines = ["<b>Расписание (дата → слоты)</b>", ""]
    for d in sorted(by_date.keys()):
        parts = []
        for t, is_booked in by_date[d]:
            label = t.strftime("%H:%M")
            if is_booked:
                label += " (занято)"
            parts.append(label)
        lines.append(f"<b>{d.day}/{d.month:02d}</b>  " + ", ".join(parts))
    return "\n".join(lines)


@router.message(Command("schedule"))
async def cmd_schedule(message: Message) -> None:
    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        master = (
            db.query(MasterProfileORM)
            .filter(MasterProfileORM.user_id == message.from_user.id)
            .one_or_none()
        )
        if master is None:
            await message.answer("Сначала пройдите онбординг через /start.")
            return

        slots = (
            db.query(AvailabilitySlotORM)
            .filter(AvailabilitySlotORM.master_id == master.id)
            .order_by(AvailabilitySlotORM.slot_date, AvailabilitySlotORM.slot_time)
            .all()
        )
        if not slots:
            await message.answer(
                "Расписание пока не настроено.\n\n"
                "Формат — дата и время слотов (можно несколько строк):\n"
                "<b>Д/ММ в ЧЧ:ММ</b> или <b>Д/ММ в ЧЧ:ММ, ЧЧ:ММ, ...</b>\n"
                "Например:\n"
                "9/02 в 10:00\n"
                "20/02 в 10:00, 12:00, 16:00"
            )
            return

        # Занятые слоты из записей (дата+время в таймзоне мастера)
        tz = ZoneInfo(master.timezone)
        bookings = (
            db.query(BookingORM)
            .filter(BookingORM.master_id == master.id)
            .all()
        )
        booked_set: set[tuple[date, time]] = set()
        for b in bookings:
            local = b.start_at.astimezone(tz)
            booked_set.add((local.date(), time(local.hour, local.minute)))

        slot_list = [(s.slot_date, s.slot_time) for s in slots]
        formatted = _format_schedule_with_bookings(slot_list, booked_set)
        await message.answer(formatted + "\n\nДобавить слоты: отправьте строку вида 20/02 в 10:00, 12:00")
    finally:
        db.close()


@router.message(
    F.text,
    lambda m: " в " in (m.text or "") and len(parse_schedule_lines((m.text or "").strip())) > 0,
)
async def add_slots_from_text(message: Message) -> None:
    text = (message.text or "").strip()
    if not text or " в " not in text:
        return

    parsed = parse_schedule_lines(text)
    if not parsed:
        return

    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        master = (
            db.query(MasterProfileORM)
            .filter(MasterProfileORM.user_id == message.from_user.id)
            .one_or_none()
        )
        if master is None:
            return

        added = 0
        for slot_date, slot_time in parsed:
            exists = (
                db.query(AvailabilitySlotORM)
                .filter(
                    AvailabilitySlotORM.master_id == master.id,
                    AvailabilitySlotORM.slot_date == slot_date,
                    AvailabilitySlotORM.slot_time == slot_time,
                )
                .first()
            )
            if not exists:
                db.add(
                    AvailabilitySlotORM(
                        master_id=master.id,
                        slot_date=slot_date,
                        slot_time=slot_time,
                    )
                )
                added += 1
        db.commit()

        await message.answer(
            f"Добавлено слотов: {added}.\nПосмотреть: /schedule"
        )
    finally:
        db.close()

