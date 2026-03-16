from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.base import get_session_maker
from app.db.models import MasterProfileORM

router = Router()


@router.message(Command("share"))
async def cmd_share(message: Message) -> None:
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

        link = f"t.me/<bot_username>?start=master_{master.slug}"
        text = (
            "Ваша персональная ссылка для клиентов:\n"
            f"{link}\n\n"
            "Готовый текст для отправки:\n"
            "«Я принимаю записи через Telegram-бота. Нажмите на ссылку и выберите удобное время: "
            f"{link}»"
        )
        await message.answer(text)
    finally:
        db.close()

