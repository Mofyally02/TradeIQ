from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://tradeiq:change-me@localhost:5432/tradeiq"
    web_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    session_cookie_name: str = "tradeiq_session"
    session_ttl_hours: int = Field(default=168, ge=1, le=720)
    cookie_secure: bool = False
    environment: Literal["development", "test", "production"] = "development"
    credential_encryption_key: str | None = None
    public_api_url: str = "http://localhost:8000"
    metaapi_token: str | None = None
    metaapi_history_days: int = Field(default=365, ge=1, le=3650)
    metaapi_sync_interval_seconds: int = Field(default=120, ge=30, le=86400)

    @model_validator(mode="after")
    def require_secure_cookie_in_production(self) -> "Settings":
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production")
        if self.environment == "production" and not self.database_url.startswith("postgresql"):
            raise ValueError("A PostgreSQL DATABASE_URL is required in production")
        if self.environment == "production" and not self.credential_encryption_key:
            raise ValueError("CREDENTIAL_ENCRYPTION_KEY must be set in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
