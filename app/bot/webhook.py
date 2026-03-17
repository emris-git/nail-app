from __future__ import annotations

import logging
import sys
import traceback

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import Response

from aiogram import Bot, Dispatcher
from aiogram.types import Update

from app.config.settings import Settings

logger = logging.getLogger(__name__)


def setup_webhook_routes(app: FastAPI, bot: Bot, dispatcher: Dispatcher, settings: Settings) -> None:
    router = APIRouter()

    webhook_path = f"/webhook/{settings.bot_webhook_secret}"

    @router.post(webhook_path)
    async def telegram_webhook(request: Request) -> Response:
        body: dict | None = None
        try:
            body = await request.json()
            update_id = body.get("update_id", "?")
            logger.info("Webhook received update_id=%s", update_id)
            print(f"[WEBHOOK] update_id={update_id}", flush=True)
            update = Update.model_validate(body)
            await dispatcher.feed_update(bot=bot, update=update)
            return Response(status_code=200)
        except Exception as e:
            update_id = body.get("update_id", "?") if isinstance(body, dict) else "?"
            logger.exception("Webhook handler error update_id=%s: %s", update_id, e)
            print(f"[WEBHOOK ERROR] update_id={update_id}: {e!r}", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            raise

    app.include_router(router)

