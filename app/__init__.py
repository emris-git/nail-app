"""
Top-level application package for the telegram beauty booking bot.

This package is organised into submodules:
- config: configuration and logging
- api: FastAPI app and HTTP-facing routes
- bot: aiogram bot wiring, handlers, keyboards, texts
- domain: pure business rules and value objects
- services: application services (use cases)
- db: persistence models, repositories, migrations glue
- adapters: integrations (LLM, image-to-text, time utilities)
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
