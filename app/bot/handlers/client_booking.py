from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict

from aiogram import Router
from aiogram.types import Message

from app.adapters.time_utils import make_timezone
from app.config import get_settings
from app.db.base import get_session_maker
from app.db.models import (
    BookingORM,
    ClientProfileORM,
    MasterProfileORM,
    ServiceORM,
)

router = Router()


@dataclass
class ClientState:
    master_id: int
    stage: str
    chosen_service_id: int | None = None


_CLIENT_STATES: Dict[int, ClientState] = {}


def set_client_state(user_id: int, state: ClientState) -> None:
    _CLIENT_STATES[user_id] = state


def get_client_state(user_id: int) -> ClientState | None:
    return _CLIENT_STATES.get(user_id)


def clear_client_state(user_id: int) -> None:
    _CLIENT_STATES.pop(user_id, None)


@router.message()
async def handle_client_flow(message: Message) -> None:
    user_id = message.from_user.id
    state = get_client_state(user_id)
    if state is None:
        return

    db_session_maker = get_session_maker()
    db = db_session_maker()
    try:
        if state.stage == "choose_service":
            try:
                index = int(message.text.strip()) - 1
            except ValueError:
                await message.answer("Пожалуйста, отправьте номер услуги из списка.")
                return

            services = (
                db.query(ServiceORM)
                .filter(ServiceORM.master_id == state.master_id, ServiceORM.is_active.is_(True))
                .order_by(ServiceORM.id)
                .all()
            )
            if index < 0 or index >= len(services):
                await message.answer("Нет услуги с таким номером. Попробуйте ещё раз.")
                return

            service = services[index]
            state.chosen_service_id = service.id
            state.stage = "enter_datetime"
            set_client_state(user_id, state)

            await message.answer(
                "Вы выбрали услугу:\n"
                f"{service.name} — {int(service.price)} ₽, {service.duration_minutes} мин.\n\n"
                "Теперь отправьте желаемую дату и время в формате:\n"
                "<b>ДД.ММ ЧЧ:ММ</b>\n"
                "Например: 25.03 14:30"
            )
            return

        if state.stage == "enter_datetime":
            try:
                date_str, time_str = message.text.strip().split()
                day, month = map(int, date_str.split("."))
                hour, minute = map(int, time_str.split(":"))
            except ValueError:
                await message.answer("Не удалось разобрать дату и время. Попробуйте ещё раз.")
                return

            now = datetime.now()
            local_tz = make_timezone(get_settings().default_timezone)
            start_local = datetime(
                year=now.year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                tzinfo=local_tz,
            )

            service = db.get(ServiceORM, state.chosen_service_id)
            master = db.get(MasterProfileORM, state.master_id)
            if service is None or master is None:
                await message.answer("Ошибка при создании записи. Попробуйте позже.")
                clear_client_state(user_id)
                return

            end_local = start_local + timedelta(minutes=service.duration_minutes)

            client = (
                db.query(ClientProfileORM)
                .filter(ClientProfileORM.tg_user_id == user_id)
                .one_or_none()
            )
            if client is None:
                client = ClientProfileORM(
                    tg_user_id=user_id,
                    name=message.from_user.full_name or "Клиент",
                    username=message.from_user.username,
                )
                db.add(client)
                db.flush()

            booking = BookingORM(
                master_id=master.id,
                client_id=client.id,
                service_id=service.id,
                start_at=start_local.astimezone(datetime.timezone.utc),
                end_at=end_local.astimezone(datetime.timezone.utc),
                status="CONFIRMED",
            )
            db.add(booking)
            db.commit()

            await message.answer(
                "Запись создана!\n\n"
                f"Мастер: {master.display_name}\n"
                f"Услуга: {service.name}\n"
                f"Дата и время: {start_local.strftime('%d.%m %H:%M')}\n"
            )
            clear_client_state(user_id)
    finally:
        db.close()

