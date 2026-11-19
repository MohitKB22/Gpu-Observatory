"""Application settings, loaded from environment variables (and `.env` in development)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_DEFAULT_SECRET = "change-me-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    database_url: str = "postgresql+psycopg://observatory:observatory@localhost:5432/observatory"
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=10, ge=0, le=100)

    # Used to encrypt endpoint API keys at rest. Rotating it makes stored keys unreadable.
    secret_key: str = INSECURE_DEFAULT_SECRET

    # Comma-separated list, e.g. "http://localhost:5173,https://observatory.example.com"
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    demo_mode: bool = True
    demo_seed_history: bool = True
    demo_simulate_latency: bool = True

    health_check_interval_seconds: int = Field(default=60, ge=0)  # 0 disables the scheduler
    health_check_retention_days: int = Field(default=7, ge=1)
    system_sample_interval_seconds: float = Field(default=5.0, gt=0)
    system_history_size: int = Field(default=720, ge=10)  # 720 samples x 5s = 1 hour

    vllm_metrics_timeout_seconds: float = Field(default=3.0, gt=0)
    nvidia_smi_path: str = "nvidia-smi"
    web_concurrency: int = Field(default=1, ge=1)

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        # Hosted Postgres providers usually hand out postgres:// or postgresql:// URLs.
        # SQLAlchemy needs the driver named explicitly; psycopg 3 serves both sync and async.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    @model_validator(mode="after")
    def require_real_secret_in_production(self) -> "Settings":
        weak_secret = self.secret_key == INSECURE_DEFAULT_SECRET or len(self.secret_key) < 32
        if self.app_env == "production" and weak_secret:
            raise ValueError(
                "SECRET_KEY must be set to a random value of at least 32 characters in production "
                "(for example: openssl rand -hex 32)"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
