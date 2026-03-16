from __future__ import annotations

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .handlers import (
    client_booking,
    start,
    master_services,
    master_schedule,
    master_share,
    master_bookings,
    master_clients,
)


def create_bot_and_dispatcher(token: str) -> tuple[Bot, Dispatcher]:
    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(client_booking.router)
    dp.include_router(start.router)
    dp.include_router(master_services.router)
    dp.include_router(master_schedule.router)
    dp.include_router(master_share.router)
    dp.include_router(master_bookings.router)
    dp.include_router(master_clients.router)
    return bot, dp

