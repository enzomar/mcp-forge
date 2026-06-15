from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    BASE_URL: str = "http://localhost:8000"

    STORAGE_PATH: str = "storage/outputs"
    TEMP_PATH: str = "storage/tmp"

    SECRET_KEY: str = Field(default="change-me-in-production")
    TOKEN_EXPIRY_HOURS: int = 6

    MAX_FILE_SIZE_MB: int = 10
    RATE_LIMIT_GENERATE: str = "5/minute"

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_USE_TLS: bool = True
    EMAIL_FROM: str = "noreply@mcpforge.io"
    EMAIL_FROM_NAME: str = "MCP Forge"


settings = Settings()
