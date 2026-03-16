from __future__ import annotations

from datetime import time

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.base import get_session_maker
from app.db.models import MasterProfileORM, WorkingWindowORM

router = Router()


@router.message(Command("schedule"))
async def cmd_schedule(message: Message) -> None:
    """
    Простое расписание:
    - /schedule — показать текущие окна.
    - Для добавления окна отправьте:
      weekday; HH:MM; HH:MM
      Например: 1; 10:00; 18:00 (1 = Пн).
    """
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

        windows = (
            db.query(WorkingWindowORM)
            .filter(WorkingWindowORM.master_id == master.id)
            .order_by(WorkingWindowORM.weekday, WorkingWindowORM.start_time)
            .all()
        )
        if not windows:
            await message.answer(
                "Расписание пока не настроено.\n\n"
                "Чтобы добавить окно, отправьте сообщение вида:\n"
                "<b>weekday; HH:MM; HH:MM</b>\n"
                "Например:\n"
                "1; 10:00; 18:00  (1 = Пн, 2 = Вт и т.д.)"
            )
            return

        lines = ["Текущие рабочие окна:"]
        for w in windows:
            lines.append(f"- День {w.weekday}: {w.start_time.strftime('%H:%M')}–{w.end_time.strftime('%H:%M')}")
        await message.answer("\n".join(lines))
    finally:
        db.close()


@router.message()
async def add_window_from_text(message: Message) -> None:
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

        parts = [p.strip() for p in message.text.split(";")]
        if len(parts) != 3:
            return

        weekday_str, start_str, end_str = parts
        try:
            weekday = int(weekday_str)
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
        except ValueError:
            return

        start_t = time(start_h, start_m)
        end_t = time(end_h, end_m)
        if end_t <= start_t:
            return

        window = WorkingWindowORM(
            master_id=master.id,
            weekday=weekday,
            start_time=start_t,
            end_time=end_t,
        )
        db.add(window)
        db.commit()

        await message.answer(
            f"Добавлено окно: день {weekday}, {start_t.strftime('%H:%M')}–{end_t.strftime('%H:%M')}.\n"
            "Посмотреть расписание: /schedule"
        )
    finally:
        db.close()

