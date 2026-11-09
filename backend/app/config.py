"""Read settings from the root .env file. Defaults work with the local launcher."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")
    database_url: str = "postgresql+psycopg://jev:jev_local@127.0.0.1:5432/jev"
    decision_provider: Literal["mock", "jev"] = "mock"
    typesafe_api_key: SecretStr | None = None
    jev_model: str = "jev-latest"
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    request_timeout_seconds: float = Field(default=30, gt=0, le=120)
    max_retries: int = Field(default=2, ge=0, le=5)
    candidate_filter_budget: int = Field(default=30, ge=1, le=100)
    select_threshold: float = Field(default=0.7, ge=0, le=1)
    reject_threshold: float = Field(default=0.3, ge=0, le=1)
    max_filters_per_category: int = Field(default=10, ge=1, le=100)

    @model_validator(mode="after")
    def validate_policy(self):
        if self.reject_threshold >= self.select_threshold:
            raise ValueError("reject_threshold must be below select_threshold")
        if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("PostgreSQL is required; configure DATABASE_URL")
        return self

    @property
    def provider_ready(self) -> bool:
        if self.decision_provider == "mock":
            return True
        if self.typesafe_api_key is None:
            return False
        return bool(self.typesafe_api_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
