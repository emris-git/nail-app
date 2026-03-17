from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.bot.parsers import parse_schedule_lines, parse_services_text
from app.bot.texts import ru
from app.config import get_settings
from app.db.base import get_session_maker
from app.db.models import (
    AvailabilitySlotORM,
    ClientSavedMasterORM,
    MasterProfileORM,
    ServiceORM,
)
from app.adapters.llm.mock import MockPriceListParser
from app.services.master_service import MasterOnboardingService
from .client_booking import ClientState, set_client_state

router = Router()

# Выбор роли при /start без payload
_ROLE_CHOICE_PENDING: set[int] = set()

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
    user_id = message.from_user.id

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

            # Добавляем мастера в список клиента (по ссылке)
            saved = (
                db.query(ClientSavedMasterORM)
                .filter(
                    ClientSavedMasterORM.tg_user_id == user_id,
                    ClientSavedMasterORM.master_id == master.id,
                )
                .first()
            )
            if not saved:
                db.add(
                    ClientSavedMasterORM(tg_user_id=user_id, master_id=master.id)
                )
                db.commit()

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
                "Выберите услугу (номер):",
            ]
            for idx, s in enumerate(services, start=1):
                lines.append(f"{idx}. {s.name} — {int(s.price)}, {s.duration_minutes} мин")

            set_client_state(
                user_id,
                ClientState(master_id=master.id, stage="choose_service"),
            )

            await message.answer("\n".join(lines))
            return
        finally:
            db.close()

    # Нет payload — кнопки (и текст как запасной вариант)
    _ROLE_CHOICE_PENDING.add(user_id)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мастер", callback_data="role:master")],
        [InlineKeyboardButton(text="Клиент", callback_data="role:client")],
    ])
    await message.answer("Кем вы являетесь?", reply_markup=keyboard)


@router.callback_query(F.data.in_({"role:master", "role:client"}))
async def handle_role_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    user_id = callback.from_user.id
    _ROLE_CHOICE_PENDING.discard(user_id)
    if callback.data == "role:master":
        await callback.message.answer(ru.MASTER_ENTER_NAME)
        return
    # role:client
    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        masters = (
            db.query(MasterProfileORM)
            .join(
                ClientSavedMasterORM,
                (ClientSavedMasterORM.master_id == MasterProfileORM.id)
                & (ClientSavedMasterORM.tg_user_id == user_id),
            )
            .order_by(MasterProfileORM.display_name)
            .all()
        )
        if not masters:
            await callback.message.answer(ru.CLIENT_NO_MASTERS)
            return
        set_client_state(
            user_id,
            ClientState(
                master_id=0,
                stage="choose_master",
                master_ids=[m.id for m in masters],
            ),
        )
        lines = [ru.CLIENT_CHOOSE_MASTER, ""]
        for idx, m in enumerate(masters, start=1):
            lines.append(f"{idx}. {m.display_name}")
        await callback.message.answer("\n".join(lines))
    finally:
        db.close()


@router.message(
    F.text & ~F.via_bot,
    lambda m: m.from_user.id in _ROLE_CHOICE_PENDING,
)
async def handle_role_choice(message: Message) -> None:
    user_id = message.from_user.id
    _ROLE_CHOICE_PENDING.discard(user_id)
    text = (message.text or "").strip().lower()

    if text in ("мастер", "1", "master"):
        await message.answer(ru.MASTER_ENTER_NAME)
        return

    if text in ("клиент", "2", "client"):
        db_session_maker = get_session_maker()
        db = db_session_maker()
        try:
            masters = (
                db.query(MasterProfileORM)
                .join(
                    ClientSavedMasterORM,
                    (ClientSavedMasterORM.master_id == MasterProfileORM.id)
                    & (ClientSavedMasterORM.tg_user_id == user_id),
                )
                .order_by(MasterProfileORM.display_name)
                .all()
            )
            if not masters:
                await message.answer(ru.CLIENT_NO_MASTERS)
                return
            set_client_state(
                user_id,
                ClientState(
                    master_id=0,
                    stage="choose_master",
                    master_ids=[m.id for m in masters],
                ),
            )
            lines = [ru.CLIENT_CHOOSE_MASTER, ""]
            for idx, m in enumerate(masters, start=1):
                lines.append(f"{idx}. {m.display_name}")
            await message.answer("\n".join(lines))
        finally:
            db.close()
        return

    _ROLE_CHOICE_PENDING.add(user_id)
    await message.answer("Напишите <b>мастер</b> или <b>клиент</b> (или 1 / 2).")


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
            await message.answer(ru.MASTER_COMMANDS)
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
        parsed = parse_schedule_lines(text)
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

