from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.parsers import format_schedule_slots, parse_schedule_lines
from app.db.base import get_session_maker
from app.db.models import AvailabilitySlotORM, MasterProfileORM

router = Router()


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

        formatted = format_schedule_slots([(s.slot_date, s.slot_time) for s in slots])
        await message.answer("Ваши слоты:\n\n" + formatted)
    finally:
        db.close()


@router.message()
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

