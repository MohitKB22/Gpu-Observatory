"""Time-range parsing and bucket selection for dashboard queries.

Bucket width is chosen from the range so a dashboard request never scans
millions of raw points -- the aggregation layer required by section 36.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.core.errors import ValidationError

_RANGE_RE = re.compile(r"^(\d+)(s|m|h|d|w)$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}

PRESET_RANGES = ["5m", "15m", "1h", "6h", "24h", "7d"]
MAX_RANGE_SECONDS = 90 * 86400
MAX_POINTS = 720


@dataclass(frozen=True)
class TimeRange:
    start: datetime
    end: datetime
    bucket_seconds: int
    label: str

    @property
    def duration_seconds(self) -> int:
        return max(1, int((self.end - self.start).total_seconds()))

    @property
    def estimated_points(self) -> int:
        return max(1, self.duration_seconds // self.bucket_seconds)


def parse_duration(value: str) -> int:
    """Parse a compact duration such as ``15m`` or ``7d`` into seconds."""
    match = _RANGE_RE.match(value.strip().lower())
    if not match:
        raise ValidationError(
            f"Invalid time range '{value}'. Use a form like 5m, 1h, 24h or 7d.",
            details={"allowed_presets": PRESET_RANGES},
        )
    amount, unit = int(match.group(1)), match.group(2)
    seconds = amount * _UNIT_SECONDS[unit]
    if seconds <= 0:
        raise ValidationError("Time range must be positive.")
    if seconds > MAX_RANGE_SECONDS:
        raise ValidationError(
            "Time range exceeds the maximum of 90 days.",
            details={"max_seconds": MAX_RANGE_SECONDS},
        )
    return seconds


def choose_bucket_seconds(duration_seconds: int) -> int:
    """Pick the smallest sane bucket that keeps the series under MAX_POINTS."""
    candidates = [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 21600, 86400]
    for candidate in candidates:
        if duration_seconds / candidate <= MAX_POINTS:
            return candidate
    return candidates[-1]


def resolve_range(
    range_str: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    bucket_seconds: int | None = None,
) -> TimeRange:
    """Resolve either a preset range or an explicit custom start/end window."""
    now = datetime.now(timezone.utc)

    if start and end:
        if start >= end:
            raise ValidationError("`start` must be strictly before `end`.")
        start = (
            start.astimezone(timezone.utc) if start.tzinfo else start.replace(tzinfo=timezone.utc)
        )
        end = end.astimezone(timezone.utc) if end.tzinfo else end.replace(tzinfo=timezone.utc)
        duration = int((end - start).total_seconds())
        if duration > MAX_RANGE_SECONDS:
            raise ValidationError(
                "Custom range exceeds the maximum of 90 days.",
                details={"max_seconds": MAX_RANGE_SECONDS},
            )
        label = "custom"
    elif start or end:
        raise ValidationError("`start` and `end` must be supplied together.")
    else:
        label = range_str or "1h"
        duration = parse_duration(label)
        end = now
        start = now - timedelta(seconds=duration)

    bucket = bucket_seconds or choose_bucket_seconds(duration)
    if bucket < 1:
        raise ValidationError("`bucket_seconds` must be at least 1.")
    if duration / bucket > MAX_POINTS * 4:
        raise ValidationError(
            "The requested bucket size would return too many points.",
            details={"max_points": MAX_POINTS * 4},
        )
    return TimeRange(start=start, end=end, bucket_seconds=bucket, label=label)


def floor_to_bucket(moment: datetime, bucket_seconds: int) -> datetime:
    """Align a timestamp down to the start of its bucket."""
    epoch = int(moment.timestamp())
    return datetime.fromtimestamp(epoch - (epoch % bucket_seconds), tz=timezone.utc)
