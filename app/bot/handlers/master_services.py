from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.parsers import parse_services_text
from app.db.base import get_session_maker
from app.db.models import MasterProfileORM, ServiceORM

router = Router()


def _services_list_text(services: list) -> str:
    lines = ["<b>Ваши услуги:</b>"]
    for idx, s in enumerate(services, start=1):
        lines.append(f"{idx}. {s.name} — {int(s.price)}, {s.duration_minutes} мин")
    lines.append("")
    lines.append(
        "Добавить: отправьте строку <b>название, цена, длительность</b> (можно несколько строк)."
    )
    lines.append("Удалить: отправьте <b>УДАЛИТЬ</b> и номер услуги (например: УДАЛИТЬ 2).")
    return "\n".join(lines)


@router.message(Command("services"))
async def cmd_services(message: Message) -> None:
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

        services = (
            db.query(ServiceORM)
            .filter(ServiceORM.master_id == master.id, ServiceORM.is_active.is_(True))
            .order_by(ServiceORM.id)
            .all()
        )

        if not services:
            await message.answer(
                "У вас пока нет услуг.\n\n"
                "Добавить: отправьте строку в формате\n"
                "<b>название, цена, длительность_мин</b> (запятая). Можно с валютой, несколько строк:\n"
                "Маникюр, 200 MYR, 60\n"
                "Педикюр, 180 MYR, 60"
            )
            return

        await message.answer(_services_list_text(services))
    finally:
        db.close()


@router.message(F.text, lambda m: (m.text or "").strip().upper().startswith("УДАЛИТЬ"))
async def remove_service_by_number(message: Message) -> None:
    text = (message.text or "").strip()
    rest = text[7:].strip()  # после "УДАЛИТЬ" (7 символов)
    try:
        num = int(rest.split()[0])
    except (ValueError, IndexError):
        await message.answer("Напишите: УДАЛИТЬ и номер услуги (например: УДАЛИТЬ 2).")
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
            await message.answer("Сначала пройдите онбординг через /start.")
            return
        services = (
            db.query(ServiceORM)
            .filter(ServiceORM.master_id == master.id, ServiceORM.is_active.is_(True))
            .order_by(ServiceORM.id)
            .all()
        )
        if num < 1 or num > len(services):
            await message.answer(f"Нет услуги с номером {num}. Отправьте /services для списка.")
            return
        service = services[num - 1]
        service.is_active = False
        db.commit()
        await message.answer(f"Услуга «{service.name}» отключена. Список: /services")
    finally:
        db.close()


@router.message(F.text, lambda m: len(parse_services_text((m.text or "").strip())) > 0)
async def add_service_from_text(message: Message) -> None:
    text = (message.text or "").strip()
    if not text:
        return
    parsed = parse_services_text(text)
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

        added = []
        for name, price, duration in parsed:
            service = ServiceORM(
                master_id=master.id,
                name=name,
                price=price,
                duration_minutes=duration,
                is_active=True,
            )
            db.add(service)
            added.append(f"{name} — {int(price)}, {duration} мин")
        db.commit()

        msg = "Добавлено:\n" + "\n".join(added) + "\n\nСписок: /services"
        await message.answer(msg)
    finally:
        db.close()

