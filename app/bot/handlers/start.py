from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from app.bot.parsers import parse_schedule_lines, parse_services_text
from app.bot.texts import ru
from app.config import get_settings
from app.db.base import get_session_maker
from app.db.models import (
    AvailabilitySlotORM,
    MasterProfileORM,
    ServiceORM,
)
from app.adapters.llm.mock import MockPriceListParser
from app.services.master_service import MasterOnboardingService

router = Router()

# Labels for master command buttons (reply keyboard)
_BTN_MY_SERVICES = "Мои услуги"
_BTN_SLOTS = "Слоты"
_BTN_BOOKINGS = "Записи"
_BTN_CLIENTS = "Клиенты"
_BTN_LINK = "Ссылка для клиента"
_MASTER_MENU_TEXTS: set[str] = {
    _BTN_MY_SERVICES,
    _BTN_SLOTS,
    _BTN_BOOKINGS,
    _BTN_CLIENTS,
    _BTN_LINK,
}

# Ожидание имени мастера (после /start)
_EXPECT_MASTER_NAME: set[int] = set()

# Онбординг мастера: после имени — услуги, затем расписание
_MASTER_ONBOARDING: dict[int, tuple[int, str]] = {}  # user_id -> (master_id, "services" | "schedule")


def _get_master_onboarding(user_id: int) -> tuple[int, str] | None:
    return _MASTER_ONBOARDING.get(user_id)


def _set_master_onboarding(user_id: int, master_id: int, step: str) -> None:
    _MASTER_ONBOARDING[user_id] = (master_id, step)


def _clear_master_onboarding(user_id: int) -> None:
    _MASTER_ONBOARDING.pop(user_id, None)


def _build_client_bot_link(payload: str = "") -> str | None:
    """
    Returns a deep link to the public client bot, or None if CLIENT_BOT_USERNAME is not configured.
    payload should be a raw /start payload without leading spaces.
    """
    username = get_settings().client_bot_username
    if not username:
        return None
    payload_part = f"?start={payload}" if payload else ""
    return f"https://t.me/{username}{payload_part}"


async def _answer_client_redirect(message: Message, payload: str = "") -> None:
    link = _build_client_bot_link(payload=payload)
    if not link:
        await message.answer(
            "Клиентская запись вынесена в отдельный бот.\n\n"
            "Админ: задайте переменную окружения <b>CLIENT_BOT_USERNAME</b> для ссылки на клиентский бот."
        )
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Открыть клиентский бот", url=link)],
        ]
    )
    await message.answer(
        "Для записи, выбора услуг и слотов перейдите в клиентский бот:\n"
        f"{link}",
        reply_markup=keyboard,
    )


def _master_commands_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        resize_keyboard=True,
        keyboard=[
            [KeyboardButton(text=_BTN_MY_SERVICES), KeyboardButton(text=_BTN_SLOTS)],
            [KeyboardButton(text=_BTN_BOOKINGS), KeyboardButton(text=_BTN_CLIENTS)],
            [KeyboardButton(text=_BTN_LINK)],
        ],
    )


@router.message(
    F.text,
    lambda m: (m.text or "").strip() in _MASTER_MENU_TEXTS,
)
async def master_menu_buttons(message: Message) -> None:
    text = (message.text or "").strip()
    # local imports to avoid circular imports at module load time
    from app.bot.handlers import master_bookings, master_clients, master_schedule, master_services, master_share

    if text == _BTN_MY_SERVICES:
        await master_services.cmd_services(message)
        return
    if text == _BTN_SLOTS:
        await master_schedule.cmd_schedule(message)
        return
    if text == _BTN_BOOKINGS:
        await master_bookings.cmd_bookings(message)
        return
    if text == _BTN_CLIENTS:
        await master_clients.cmd_clients(message)
        return
    if text == _BTN_LINK:
        await master_share.cmd_share(message)
        return


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    payload = parts[1] if len(parts) > 1 else ""
    user_id = message.from_user.id

    if payload.startswith("master_"):
        # Клиентский flow вынесен в отдельный публичный бот — просто редиректим с тем же payload.
        await _answer_client_redirect(message, payload=payload)
        return

    # Роль больше не выбираем: этот бот только для мастеров.
    # Если мастер уже существует — показываем команды; иначе начинаем онбординг.
    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        master = (
            db.query(MasterProfileORM)
            .filter(MasterProfileORM.user_id == user_id)
            .one_or_none()
        )
    finally:
        db.close()

    if master is not None:
        await message.answer(ru.MASTER_COMMANDS, reply_markup=_master_commands_keyboard())
        return

    _EXPECT_MASTER_NAME.add(user_id)
    await message.answer(ru.MASTER_ENTER_NAME, reply_markup=_master_commands_keyboard())


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

    # Allow menu buttons to be handled by master_menu_buttons.
    if text in _MASTER_MENU_TEXTS:
        return

    # Не перехватываем команды во время онбординга (кроме /готово),
    # чтобы /services, /schedule и другие команды работали всегда.
    if text.startswith("/") and text != "/готово":
        return

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
            link = _build_client_bot_link(payload=f"master_{slug}")
            if not link:
                await message.answer(
                    f"{ru.MASTER_ONBOARDING_DONE}\n\n"
                    "Админ: задайте переменную окружения <b>CLIENT_BOT_USERNAME</b>, "
                    "чтобы формировать ссылку на клиентский бот."
                )
                await message.answer(ru.MASTER_COMMANDS)
                return
            await message.answer(
                f"{ru.MASTER_ONBOARDING_DONE}\n\n"
                "Ваша личная ссылка для клиентов:\n"
                f"{link}"
            )
            await message.answer(ru.MASTER_COMMANDS, reply_markup=_master_commands_keyboard())
        return

    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        if step == "services":
            parsed = parse_services_text(text)
            if not parsed:
                await message.answer(
                    "Формат: название, цена, длительность_мин (через запятую).\n"
                    "Можно с валютой и несколько строк. Например:\n"
                    "Маникюр, 200 MYR, 60"
                )
                return
            added = []
            for name, price, duration in parsed:
                service = ServiceORM(
                    master_id=master_id,
                    name=name,
                    price=price,
                    duration_minutes=duration,
                    is_active=True,
                )
                db.add(service)
                added.append(f"{name} — {int(price)}, {duration} мин")
            db.commit()
            await message.answer(
                "Добавлено:\n" + "\n".join(added) + "\n\nЕщё или /готово"
            )
            return

        # step == "schedule"
        master = db.query(MasterProfileORM).filter(MasterProfileORM.id == master_id).one_or_none()
        master_tz = master.timezone if master is not None else get_settings().default_timezone
        today_local = datetime.now(ZoneInfo(master_tz)).date()
        parsed = parse_schedule_lines(text, today=today_local, skip_past=True)
        if not parsed:
            await message.answer(
                "Формат: Д/ММ в ЧЧ:ММ или Д/ММ в ЧЧ:ММ, ЧЧ:ММ, ...\n"
                "Например: 20/02 в 10:00, 12:00, 16:00"
            )
            return
        added = 0
        for slot_date, slot_time in parsed:
            exists = (
                db.query(AvailabilitySlotORM)
                .filter(
                    AvailabilitySlotORM.master_id == master_id,
                    AvailabilitySlotORM.slot_date == slot_date,
                    AvailabilitySlotORM.slot_time == slot_time,
                )
                .first()
            )
            if not exists:
                db.add(
                    AvailabilitySlotORM(
                        master_id=master_id,
                        slot_date=slot_date,
                        slot_time=slot_time,
                    )
                )
                added += 1
        db.commit()
        await message.answer(
            f"Добавлено слотов: {added}.\nЕщё или /готово"
        )
    finally:
        db.close()


@router.message(F.text & ~F.via_bot, lambda m: m.from_user.id in _EXPECT_MASTER_NAME)
async def master_enter_name(message: Message) -> None:
    """
    Первый текст после /start без payload — имя мастера; затем запускаем настройку услуг и расписания.
    """
    user_id = message.from_user.id
    text = (message.text or "").strip()
    if text in _MASTER_MENU_TEXTS:
        await message.answer(ru.MASTER_ENTER_NAME, reply_markup=_master_commands_keyboard())
        return
    # Команды не считаем именем: оставляем ожидание имени активным
    if text.startswith("/"):
        await message.answer(ru.MASTER_ENTER_NAME)
        return

    _EXPECT_MASTER_NAME.discard(user_id)

    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        service = MasterOnboardingService(db=db, price_list_parser=MockPriceListParser())
        result = await service.create_master_profile(
            tg_user_id=message.from_user.id,
            display_name=text,
            timezone=get_settings().default_timezone,
        )
    finally:
        db.close()

    _set_master_onboarding(message.from_user.id, result.master_id, "services")
    await message.answer(ru.MASTER_ONBOARDING_SERVICES)

