from __future__ import annotations

from fastapi import FastAPI

from app.config import configure_logging, get_settings
from app.bot.bot_factory import create_bot_and_dispatcher
from app.bot.webhook import setup_webhook_routes


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(title="Telegram Beauty Booking Bot", version="0.1.0")

    bot, dispatcher = create_bot_and_dispatcher(settings.telegram_bot_token)
    setup_webhook_routes(app, bot, dispatcher, settings)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app

