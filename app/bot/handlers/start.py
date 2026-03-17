from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.texts import ru
from app.config import get_settings
from app.db.base import get_session_maker
from app.db.models import MasterProfileORM, ServiceORM
from app.adapters.llm.mock import MockPriceListParser
from app.services.master_service import MasterOnboardingService
from .client_booking import ClientState, set_client_state

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    payload = parts[1] if len(parts) > 1 else ""

    if payload.startswith("master_"):
        slug = payload.removeprefix("master_")
        db_session_maker = get_session_maker()
        db = db_session_maker()
        try:
            master = (
                db.query(MasterProfileORM)
                .filter(MasterProfileORM.slug == slug)
                .one_or_none()
            )
            if master is None:
                await message.answer("Мастер с такой ссылкой не найден.")
                return

            services = (
                db.query(ServiceORM)
                .filter(ServiceORM.master_id == master.id, ServiceORM.is_active.is_(True))
                .order_by(ServiceORM.id)
                .all()
            )
            if not services:
                await message.answer("У мастера пока нет услуг для записи.")
                return

            lines = [
                f"Запись к мастеру {master.display_name}",
                "",
                "Выберите услугу, отправив её номер:",
            ]
            for idx, s in enumerate(services, start=1):
                lines.append(f"{idx}. {s.name} — {int(s.price)} ₽, {s.duration_minutes} мин")

            set_client_state(
                message.from_user.id,
                ClientState(master_id=master.id, stage="choose_service"),
            )

            await message.answer("\n".join(lines))
            return
        finally:
            db.close()

    await message.answer(ru.MASTER_ENTER_NAME)


@router.message(F.text & ~F.via_bot)
async def master_enter_name(message: Message) -> None:
    """
    Extremely simplified onboarding: first text after /start is treated as master display name.
    """
    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        service = MasterOnboardingService(db=db, price_list_parser=MockPriceListParser())
        result = await service.create_master_profile(
            tg_user_id=message.from_user.id,
            display_name=message.text.strip(),
            timezone=get_settings().default_timezone,
        )
    finally:
        db.close()

    bot_me = await message.bot.get_me()
    link = f"https://t.me/{bot_me.username}?start=master_{result.slug}"
    await message.answer(
        f"{ru.MASTER_ONBOARDING_DONE}\n\n"
        "Ваша личная ссылка для клиентов:\n"
        f"{link}"
    )

