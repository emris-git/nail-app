from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Core
    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    database_url: str = Field(..., alias="DATABASE_URL")
    webhook_base_url: Optional[AnyHttpUrl] = Field(None, alias="WEBHOOK_BASE_URL")
    bot_webhook_secret: str = Field("secret", alias="BOT_WEBHOOK_SECRET")
    default_timezone: str = Field("Europe/Moscow", alias="DEFAULT_TIMEZONE")

    # LLM config
    llm_provider: Literal["mock", "openai"] = Field("mock", alias="LLM_PROVIDER")
    llm_api_base: Optional[str] = Field(None, alias="LLM_API_BASE")
    llm_api_key: Optional[str] = Field(None, alias="LLM_API_KEY")
    llm_model: Optional[str] = Field(None, alias="LLM_MODEL")

    # Logging
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    # HTTP server
    port: int = Field(8000, alias="PORT")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

