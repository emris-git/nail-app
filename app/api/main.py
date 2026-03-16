from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import configure_logging, get_settings
from app.bot.bot_factory import create_bot_and_dispatcher
from app.bot.webhook import setup_webhook_routes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """При старте приложения регистрируем webhook в Telegram, если задан WEBHOOK_BASE_URL."""
    settings = get_settings()
    bot = app.state.bot
    if settings.webhook_base_url is not None:
        base = str(settings.webhook_base_url).rstrip("/")
        webhook_url = f"{base}/webhook/{settings.bot_webhook_secret}"
        try:
            await bot.set_webhook(webhook_url)
            logger.info("Telegram webhook set to %s", webhook_url)
        except Exception as e:
            logger.exception("Failed to set Telegram webhook: %s", e)
    yield
    # shutdown: можно при желании вызвать delete_webhook()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    bot, dispatcher = create_bot_and_dispatcher(settings.telegram_bot_token)

    app = FastAPI(title="Telegram Beauty Booking Bot", version="0.1.0", lifespan=lifespan)
    app.state.bot = bot
    app.state.dispatcher = dispatcher

    setup_webhook_routes(app, bot, dispatcher, settings)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app

