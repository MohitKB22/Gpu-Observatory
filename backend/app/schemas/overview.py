import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.analytics import DataScope, SummaryStats, TimeseriesPoint
from app.schemas.common import TimeWindow


class OverviewModel(BaseModel):
    id: uuid.UUID
    name: str
    provider: str
    is_demo: bool
    is_enabled: bool
    status: str
    last_checked_at: datetime | None
    requests: int
    p95_ms: float | None
    error_rate: float | None


class ModelHealthCounts(BaseModel):
    total: int
    enabled: int
    healthy: int
    unhealthy: int
    unknown: int


class SystemHealth(BaseModel):
    database_ok: bool
    database_latency_ms: float | None
    cpu_percent: float
    memory_percent: float
    gpu_available: bool
    gpu_utilization_percent: float | None
    gpu_unavailable_reason: str | None
    models: ModelHealthCounts


class OverviewResponse(BaseModel):
    window: TimeWindow
    generated_at: datetime
    bucket_seconds: int
    scope: DataScope
    summary: SummaryStats
    previous_summary: SummaryStats
    timeseries: list[TimeseriesPoint]
    models: list[OverviewModel]
    system: SystemHealth
