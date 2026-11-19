import math
from datetime import timedelta
from enum import StrEnum

from pydantic import BaseModel


class DataSource(StrEnum):
    """Which records analytics should include. Demo records are never mixed in silently:
    responses always report whether demo data contributed to the numbers."""

    REAL = "real"
    DEMO = "demo"
    ALL = "all"


class TimeWindow(StrEnum):
    LAST_HOUR = "1h"
    LAST_6_HOURS = "6h"
    LAST_24_HOURS = "24h"
    LAST_7_DAYS = "7d"

    @property
    def duration(self) -> timedelta:
        return _WINDOW_DURATIONS[self]

    @property
    def bucket_seconds(self) -> int:
        """Chart resolution: roughly 60-100 points per window."""
        return _BUCKET_SECONDS[self]


_WINDOW_DURATIONS = {
    TimeWindow.LAST_HOUR: timedelta(hours=1),
    TimeWindow.LAST_6_HOURS: timedelta(hours=6),
    TimeWindow.LAST_24_HOURS: timedelta(hours=24),
    TimeWindow.LAST_7_DAYS: timedelta(days=7),
}
_BUCKET_SECONDS = {
    TimeWindow.LAST_HOUR: 60,
    TimeWindow.LAST_6_HOURS: 5 * 60,
    TimeWindow.LAST_24_HOURS: 15 * 60,
    TimeWindow.LAST_7_DAYS: 2 * 60 * 60,
}


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class Page[ItemT](BaseModel):
    items: list[ItemT]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(self.total / self.page_size))
