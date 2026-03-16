from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

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
                "Отправьте сообщение вида:\n"
                "<b>услуга; цена; длительность_в_минутах</b>\n"
                "Например:\n"
                "Маникюр; 1500; 60"
            )
            return

        lines = ["Ваши активные услуги:"]
        for s in services:
            lines.append(f"- {s.name}: {int(s.price)} ₽, {s.duration_minutes} мин")
        await message.answer("\n".join(lines))
    finally:
        db.close()


@router.message()
async def add_service_from_text(message: Message) -> None:
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

        name, price_str, dur_str = parts
        try:
            price = float(price_str.replace(",", "."))
            duration = int(dur_str)
        except ValueError:
            return

        service = ServiceORM(
            master_id=master.id,
            name=name,
            price=price,
            duration_minutes=duration,
            is_active=True,
        )
        db.add(service)
        db.commit()

        await message.answer(
            f"Услуга добавлена:\n{name} — {int(price)} ₽, {duration} мин.\n"
            "Посмотреть список: /services"
        )
    finally:
        db.close()

