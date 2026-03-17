from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.config import get_settings
from app.db.base import get_session_maker
from app.db.models import MasterProfileORM

router = Router()


@router.message(Command("link"))
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

        username = get_settings().client_bot_username
        if not username:
            await message.answer(
                "Админ: задайте переменную окружения <b>CLIENT_BOT_USERNAME</b>, "
                "чтобы формировать ссылку на клиентский бот."
            )
            return
        link = f"https://t.me/{username}?start=master_{master.slug}"
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


# Backward-compatible alias (not advertised)
@router.message(Command("share"))
async def cmd_share_alias(message: Message) -> None:
    await cmd_share(message)

