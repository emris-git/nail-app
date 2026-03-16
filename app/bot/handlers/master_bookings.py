from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.base import get_session_maker
from app.db.models import BookingORM, ClientProfileORM, MasterProfileORM, ServiceORM

router = Router()


@router.message(Command("bookings"))
async def cmd_bookings(message: Message) -> None:
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

        bookings = (
            db.query(BookingORM)
            .filter(BookingORM.master_id == master.id)
            .order_by(BookingORM.start_at)
            .limit(20)
            .all()
        )
        if not bookings:
            await message.answer("Пока нет записей.")
            return

        lines = ["Ближайшие записи:"]
        for b in bookings:
            client = db.get(ClientProfileORM, b.client_id)
            service = db.get(ServiceORM, b.service_id)
            client_name = client.name if client else "Клиент"
            service_name = service.name if service else "Услуга"
            lines.append(
                f"- {b.start_at:%d.%m %H:%M} — {service_name} для {client_name} (статус: {b.status})"
            )
        await message.answer("\n".join(lines))
    finally:
        db.close()

