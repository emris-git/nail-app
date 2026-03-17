from __future__ import annotations

import asyncio
import sys
from typing import Optional

from uvicorn import Config, Server

from app.bot.bot_factory import create_bot_and_dispatcher
from app.config import configure_logging, get_settings


async def run_polling() -> None:
    """
    Entry point for local polling mode:

    poetry run python -m app.main --polling
    """
    configure_logging()
    settings = get_settings()
    bot, dispatcher = create_bot_and_dispatcher(settings.telegram_bot_token)

    await dispatcher.start_polling(bot)


def run_uvicorn() -> None:
    settings = get_settings()
    port = settings.port
    config = Config(app="app.asgi:app", host="0.0.0.0", port=port, reload=False)
    server = Server(config)
    asyncio.run(server.serve())


def main(argv: Optional[list[str]] = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if "--polling" in args:
        asyncio.run(run_polling())
    else:
        run_uvicorn()


if __name__ == "__main__":
    main()

