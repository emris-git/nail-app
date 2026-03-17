from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import configure_logging, get_settings
from app.bot.bot_factory import create_bot_and_dispatcher
from app.bot.webhook import setup_webhook_routes

logger = logging.getLogger(__name__)


def _log_exception(exc: BaseException) -> None:
    """Печать в stderr, чтобы точно попало в логи Railway."""
    print(f"[APP ERROR] {exc!r}", file=sys.stderr, flush=True)
    traceback.print_exc(file=sys.stderr)
    sys.stderr.flush()
    logger.exception("%s", exc)


def _run_migrations() -> None:
    """Запуск Alembic миграций (sync)."""
    from alembic import command
    from alembic.config import Config

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("script_location", "alembic")
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """При старте: миграции БД, затем регистрация webhook в Telegram."""
    try:
        await asyncio.to_thread(_run_migrations)
        logger.info("Database migrations applied")
    except Exception as e:
        logger.exception("Database migration failed: %s", e)
        raise

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

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        _log_exception(exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app

