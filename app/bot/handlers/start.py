from __future__ import annotations

from datetime import time

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.texts import ru
from app.config import get_settings
from app.db.base import get_session_maker
from app.db.models import MasterProfileORM, ServiceORM, WorkingWindowORM
from app.adapters.llm.mock import MockPriceListParser
from app.services.master_service import MasterOnboardingService
from .client_booking import ClientState, set_client_state

router = Router()

# Онбординг мастера: после имени — услуги, затем расписание
_MASTER_ONBOARDING: dict[int, tuple[int, str]] = {}  # user_id -> (master_id, "services" | "schedule")


def _get_master_onboarding(user_id: int) -> tuple[int, str] | None:
    return _MASTER_ONBOARDING.get(user_id)


def _set_master_onboarding(user_id: int, master_id: int, step: str) -> None:
    _MASTER_ONBOARDING[user_id] = (master_id, step)


def _clear_master_onboarding(user_id: int) -> None:
    _MASTER_ONBOARDING.pop(user_id, None)


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


@router.message(
    F.text & ~F.via_bot,
    lambda m: _get_master_onboarding(m.from_user.id) is not None,
)
async def master_onboarding_step(message: Message) -> None:
    """Обработка шагов онбординга: услуги и расписание после ввода имени."""
    user_id = message.from_user.id
    state = _get_master_onboarding(user_id)
    if state is None:
        return
    master_id, step = state
    text = (message.text or "").strip()

    if text == "/готово":
        if step == "services":
            _set_master_onboarding(user_id, master_id, "schedule")
            await message.answer(ru.MASTER_ONBOARDING_SCHEDULE)
            return
        # step == "schedule" -> завершаем онбординг
        _clear_master_onboarding(user_id)
        db_session_maker = get_session_maker()
        db = db_session_maker()
        try:
            master = db.query(MasterProfileORM).filter(MasterProfileORM.id == master_id).one_or_none()
            slug = master.slug if master else ""
        finally:
            db.close()
        if slug:
            bot_me = await message.bot.get_me()
            link = f"https://t.me/{bot_me.username}?start=master_{slug}"
            await message.answer(
                f"{ru.MASTER_ONBOARDING_DONE}\n\n"
                "Ваша личная ссылка для клиентов:\n"
                f"{link}"
            )
        return

    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        if step == "services":
            parts = [p.strip() for p in text.split(";")]
            if len(parts) != 3:
                await message.answer(
                    "Нужен формат: название; цена; длительность_мин\n"
                    "Например: Маникюр; 1500; 60"
                )
                return
            name, price_str, dur_str = parts
            try:
                price = float(price_str.replace(",", "."))
                duration = int(dur_str)
            except ValueError:
                await message.answer("Цена — число, длительность — целое число в минутах.")
                return
            service = ServiceORM(
                master_id=master_id,
                name=name,
                price=price,
                duration_minutes=duration,
                is_active=True,
            )
            db.add(service)
            db.commit()
            await message.answer(
                f"Добавлено: {name} — {int(price)} ₽, {duration} мин.\n"
                "Ещё услугу или /готово"
            )
            return

        # step == "schedule"
        parts = [p.strip() for p in text.split(";")]
        if len(parts) != 3:
            await message.answer(
                "Нужен формат: день_недели; HH:MM; HH:MM\n"
                "Например: 1; 10:00; 18:00 (1=Пн)"
            )
            return
        weekday_str, start_str, end_str = parts
        try:
            weekday = int(weekday_str)
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
        except ValueError:
            await message.answer("День — число 1–7, время в формате HH:MM.")
            return
        start_t = time(start_h, start_m)
        end_t = time(end_h, end_m)
        if end_t <= start_t:
            await message.answer("Время окончания должно быть позже начала.")
            return
        window = WorkingWindowORM(
            master_id=master_id,
            weekday=weekday,
            start_time=start_t,
            end_time=end_t,
        )
        db.add(window)
        db.commit()
        await message.answer(
            f"Добавлено окно: день {weekday}, {start_t.strftime('%H:%M')}–{end_t.strftime('%H:%M')}.\n"
            "Ещё окно или /готово"
        )
    finally:
        db.close()


@router.message(F.text & ~F.via_bot)
async def master_enter_name(message: Message) -> None:
    """
    Первый текст после /start без payload — имя мастера; затем запускаем настройку услуг и расписания.
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

    _set_master_onboarding(message.from_user.id, result.master_id, "services")
    await message.answer(ru.MASTER_ONBOARDING_SERVICES)

