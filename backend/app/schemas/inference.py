import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_PROMPT_CHARS = 32_000
MAX_SYSTEM_PROMPT_CHARS = 8_000
PROMPT_PREVIEW_CHARS = 160


class InferenceCreate(BaseModel):
    model_id: uuid.UUID
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARS)
    system_prompt: str | None = Field(default=None, max_length=MAX_SYSTEM_PROMPT_CHARS)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=256, ge=1, le=8192)
    # Where the request came from, for filtering logs. Seeded demo data uses a third value
    # that clients cannot submit.
    source: Literal["playground", "api"] = "api"

    @field_validator("prompt")
    @classmethod
    def prompt_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("prompt must not be blank")
        return value

    @field_validator("system_prompt")
    @classmethod
    def blank_system_prompt_is_none(cls, value: str | None) -> str | None:
        return value if value and value.strip() else None


class RequestMetricsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    latency_ms: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    token_count_source: str | None
    tokens_per_second: float | None


class InferenceRequestRead(BaseModel):
    """Full record, returned by the inference endpoint and the log detail view."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    model_id: uuid.UUID | None
    model_name: str
    provider: str
    source: str
    is_demo: bool
    status: str
    prompt: str
    system_prompt: str | None
    response_text: str | None
    temperature: float
    max_tokens: int
    error_kind: str | None
    error_message: str | None
    upstream_status_code: int | None
    metrics: RequestMetricsRead | None


class InferenceRequestListItem(BaseModel):
    """Compact row for the request log table."""

    id: uuid.UUID
    created_at: datetime
    model_id: uuid.UUID | None
    model_name: str
    provider: str
    source: str
    is_demo: bool
    status: str
    prompt_preview: str
    error_kind: str | None
    latency_ms: float | None
    total_tokens: int | None
    token_count_source: str | None
    tokens_per_second: float | None
