from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.bot.parsers import parse_services_text
from app.db.base import get_session_maker
from app.db.models import MasterProfileORM, ServiceORM

router = Router()


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
                "У вас пока нет услуг.\n"
                "Формат: <b>название, цена, длительность_мин</b> (разделитель — запятая).\n"
                "Можно с валютой и несколько строк:\n"
                "Маникюр, 200 MYR, 60\n"
                "Педикюр, 180 MYR, 60"
            )
            return

        lines = ["Ваши активные услуги:"]
        for s in services:
            lines.append(f"- {s.name}: {int(s.price)}, {s.duration_minutes} мин")
        await message.answer("\n".join(lines))
    finally:
        db.close()


@router.message()
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

