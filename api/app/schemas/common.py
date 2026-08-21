"""Shared response envelopes and primitives."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())


class PageMeta(BaseModel):
    total: int = Field(description="Total rows matching the filter.")
    limit: int
    offset: int
    has_more: bool


class Page(BaseModel, Generic[T]):
    """Standard paginated collection envelope."""

    items: list[T]
    meta: PageMeta


class DataFreshness(BaseModel):
    """Lets the UI show telemetry freshness and stale-data warnings."""

    last_sample_at: datetime | None = None
    age_seconds: float | None = None
    is_stale: bool = False
    expected_interval_seconds: float | None = None


class SeriesPoint(BaseModel):
    timestamp: datetime
    value: float | None = None


class NamedSeries(BaseModel):
    name: str
    unit: str | None = None
    entity_id: str | None = None
    entity_label: str | None = None
    points: list[SeriesPoint] = Field(default_factory=list)


class TimeSeriesResponse(BaseModel):
    range_label: str
    start: datetime
    end: datetime
    bucket_seconds: int
    data_source: str
    series: list[NamedSeries] = Field(default_factory=list)
    freshness: DataFreshness = Field(default_factory=DataFreshness)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None


class ErrorResponse(BaseModel):
    """The single error shape returned by every endpoint."""

    error: ErrorDetail


class MessageResponse(BaseModel):
    message: str


class HealthComponent(BaseModel):
    name: str
    healthy: bool
    detail: str | None = None
    latency_ms: float | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str
    demo_mode: bool
    uptime_seconds: float
    timestamp: datetime


class ReadinessResponse(BaseModel):
    status: str
    ready: bool
    components: list[HealthComponent]
    timestamp: datetime
