"""Application configuration.

All configuration is environment-driven. No secrets are ever committed; the
repository ships a `.env.example` with placeholder values only.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "development", "staging", "production", "test"]
LLMProvider = Literal["none", "openai", "anthropic", "ollama"]


class Settings(BaseSettings):
    """Runtime settings resolved from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- app ---
    APP_NAME: str = "NVIDIA AI Performance Observatory"
    ENVIRONMENT: Environment = "local"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: Literal["json", "console"] = "json"

    # ----------------------------------------------------------- database ---
    # Async SQLAlchemy URL. PostgreSQL is the production target; SQLite is
    # supported for local development and the test-suite.
    DATABASE_URL: str = "postgresql+asyncpg://nvo:nvo@localhost:5432/nvo"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_ECHO: bool = False

    # -------------------------------------------------------------- redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_ENABLED: bool = True
    CACHE_TTL_SECONDS: int = 15

    # --------------------------------------------------------------- cors ---
    CORS_ORIGINS: str = "http://localhost:3000"
    CORS_ALLOW_CREDENTIALS: bool = True

    # ----------------------------------------------------------- security ---
    # SECRET_KEY MUST be provided via environment in any non-local deployment.
    SECRET_KEY: str = Field(default="")
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    API_KEY_PREFIX: str = "nvo"
    AUTH_ENABLED: bool = True
    # Bootstrap admin, created on first startup when auth is enabled.
    BOOTSTRAP_ADMIN_EMAIL: str = "admin@localhost"
    BOOTSTRAP_ADMIN_PASSWORD: str = ""

    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_REQUESTS: int = 300
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    SECURE_HEADERS_ENABLED: bool = True
    MAX_REQUEST_BODY_BYTES: int = 1_048_576

    # ---------------------------------------------------------- telemetry ---
    GPU_METRICS_ENABLED: bool = True
    DCGM_ENABLED: bool = False
    DCGM_ENDPOINT: str = "http://localhost:9400/metrics"
    SYSTEM_METRICS_ENABLED: bool = True
    TELEMETRY_INTERVAL_SECONDS: float = 5.0
    TELEMETRY_BATCH_SIZE: int = 100
    TELEMETRY_ENABLED: bool = True
    PROMETHEUS_URL: str = "http://localhost:9090"

    # ---------------------------------------------------------- retention ---
    RETENTION_RAW_DAYS: int = 7
    RETENTION_AGGREGATED_DAYS: int = 90
    RETENTION_SUMMARY_DAYS: int = 365
    RETENTION_SWEEP_INTERVAL_SECONDS: int = 3600

    # --------------------------------------------------------------- cost ---
    COST_PER_GPU_HOUR: float = 2.50
    COST_CURRENCY: str = "USD"
    ENERGY_COST_PER_KWH: float = 0.12

    # ----------------------------------------------------------- demo mode --
    DEMO_MODE: bool = True
    DEMO_SCENARIO: str = "healthy"
    DEMO_INTERVAL_SECONDS: float = 5.0
    DEMO_GPU_COUNT: int = 4

    # ----------------------------------------------------------------- llm --
    LLM_PROVIDER: LLMProvider = "none"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_BASE_URL: str = ""
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_TOOL_ITERATIONS: int = 6

    # ---------------------------------------------------------- inference ---
    INFERENCE_BACKEND: Literal["local", "vllm", "triton", "openai"] = "local"
    INFERENCE_BASE_URL: str = ""
    INFERENCE_TIMEOUT_SECONDS: float = 60.0

    # --------------------------------------------------------- anomaly ------
    ANOMALY_ZSCORE_THRESHOLD: float = 3.0
    ANOMALY_EWMA_ALPHA: float = 0.3
    ANOMALY_MIN_SAMPLES: int = 20

    # -------------------------------------------------------- validators ----
    @field_validator("LOG_LEVEL")
    @classmethod
    def _upper_log_level(cls, v: str) -> str:
        level = v.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(f"invalid LOG_LEVEL: {v}")
        return level

    @model_validator(mode="after")
    def _validate_secrets(self) -> Settings:
        if not self.SECRET_KEY:
            if self.ENVIRONMENT in ("production", "staging"):
                raise ValueError("SECRET_KEY must be set via environment in production/staging.")
            # Ephemeral key for local/test only. Tokens do not survive restart.
            object.__setattr__(self, "SECRET_KEY", secrets.token_urlsafe(48))
        if self.ENVIRONMENT == "production" and self.DEBUG:
            raise ValueError("DEBUG must be false in production.")
        return self

    # -------------------------------------------------------- properties ----
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def sync_database_url(self) -> str:
        """Synchronous URL used by Alembic."""
        return (
            self.DATABASE_URL.replace("+asyncpg", "")
            .replace("+aiosqlite", "")
            .replace("postgresql://", "postgresql+psycopg2://")
            if self.DATABASE_URL.startswith("postgresql")
            else self.DATABASE_URL.replace("+aiosqlite", "")
        )

    @property
    def llm_enabled(self) -> bool:
        if self.LLM_PROVIDER == "none":
            return False
        if self.LLM_PROVIDER == "ollama":
            return True  # local, no key required
        return bool(self.LLM_API_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
