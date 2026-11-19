import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import DataSource, TimeWindow


class LatencyPercentiles(BaseModel):
    """Computed over successful requests only, so timeouts do not distort serving latency."""

    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None


class SummaryStats(BaseModel):
    total_requests: int
    error_requests: int
    error_rate: float | None  # 0-1, None when there were no requests
    requests_per_second: float
    latency: LatencyPercentiles
    avg_latency_ms: float | None
    # Mean per-request generation speed (completion tokens / request latency).
    avg_tokens_per_second: float | None
    # All tokens processed divided by the window length.
    token_throughput_per_second: float
    total_tokens: int
    # Share of successful requests whose token counts were reported exactly by the provider.
    exact_token_share: float | None


class TimeseriesPoint(BaseModel):
    timestamp: datetime
    requests: int
    errors: int
    error_rate: float | None
    requests_per_second: float
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    tokens: int
    token_throughput_per_second: float
    avg_tokens_per_second: float | None


class ModelComparisonRow(BaseModel):
    model_id: uuid.UUID | None  # None when the model has since been deleted
    model_name: str
    provider: str
    is_demo: bool
    stats: SummaryStats


class DataScope(BaseModel):
    """Tells the UI which data the numbers came from, so demo data is always labelled."""

    data_source: DataSource
    demo_requests: int
    real_requests: int
    includes_demo_data: bool


class AnalyticsResponse(BaseModel):
    window: TimeWindow
    start: datetime
    end: datetime
    bucket_seconds: int
    scope: DataScope
    summary: SummaryStats
    timeseries: list[TimeseriesPoint]
    models: list[ModelComparisonRow]
