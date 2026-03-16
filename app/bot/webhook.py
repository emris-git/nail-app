from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import Response

from aiogram import Bot, Dispatcher
from aiogram.types import Update

from app.config.settings import Settings


def setup_webhook_routes(app: FastAPI, bot: Bot, dispatcher: Dispatcher, settings: Settings) -> None:
    router = APIRouter()

    webhook_path = f"/webhook/{settings.bot_webhook_secret}"

    @router.post(webhook_path)
    async def telegram_webhook(request: Request) -> Response:
        body = await request.json()
        update = Update.model_validate(body)
        await dispatcher.feed_update(bot=bot, update=update)
        return Response(status_code=200)

    app.include_router(router)

