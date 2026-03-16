from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from app.db.base import get_session_maker
from app.db.models import ClientProfileORM

router = Router()


@router.message(Command("clients"))
async def cmd_clients(message: Message) -> None:
    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        clients = (
            db.query(ClientProfileORM)
            .order_by(ClientProfileORM.last_visit_at.desc().nullslast())
            .limit(20)
            .all()
        )
        if not clients:
            await message.answer("Пока нет клиентов.")
            return

        lines = ["Клиенты:"]
        for c in clients:
            last_visit = f"{c.last_visit_at:%d.%m.%Y}" if c.last_visit_at else "—"
            lines.append(f"- {c.name} (@{c.username or '—'}), последний визит: {last_visit}")
        await message.answer("\n".join(lines))
    finally:
        db.close()

