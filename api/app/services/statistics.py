"""Pure statistical helpers.

Kept dependency-free and side-effect-free so they are trivially testable and
usable from both the anomaly detector and the diagnostics rules.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def percentile(values: Sequence[float], q: float) -> float | None:
    """Linear-interpolation percentile. ``q`` is in [0, 100]."""
    clean = sorted(v for v in values if v is not None and not math.isnan(v))
    if not clean:
        return None
    if len(clean) == 1:
        return float(clean[0])
    q = max(0.0, min(100.0, q))
    rank = (q / 100.0) * (len(clean) - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return float(clean[int(rank)])
    weight = rank - low
    return float(clean[low] * (1 - weight) + clean[high] * weight)


def mean(values: Sequence[float]) -> float | None:
    clean = [v for v in values if v is not None]
    return sum(clean) / len(clean) if clean else None


def stdev(values: Sequence[float]) -> float | None:
    """Sample standard deviation (Bessel-corrected)."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    avg = sum(clean) / len(clean)
    variance = sum((v - avg) ** 2 for v in clean) / (len(clean) - 1)
    return math.sqrt(variance)


def median(values: Sequence[float]) -> float | None:
    return percentile(values, 50.0)


def mad(values: Sequence[float]) -> float | None:
    """Median absolute deviation -- robust to the outliers we are hunting."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    med = median(clean)
    if med is None:
        return None
    return median([abs(v - med) for v in clean])


def zscore(value: float, values: Sequence[float]) -> float | None:
    avg = mean(values)
    sd = stdev(values)
    if avg is None or sd is None or sd == 0:
        return None
    return (value - avg) / sd


def mean_abs_deviation(values: Sequence[float]) -> float | None:
    """Mean absolute deviation from the median."""
    clean = [v for v in values if v is not None]
    if len(clean) < 2:
        return None
    med = median(clean)
    if med is None:
        return None
    return sum(abs(v - med) for v in clean) / len(clean)


def robust_zscore(value: float, values: Sequence[float]) -> float | None:
    """Median/MAD z-score: does not get masked by the outlier itself.

    When a signal sits at a constant the MAD collapses to zero -- which is
    precisely the case where a sudden jump matters most. Fall back to a scaled
    mean absolute deviation so a pinned metric that moves is still detected.
    """
    med = median(values)
    if med is None:
        return None

    dispersion = mad(values)
    if dispersion:
        return 0.6745 * (value - med) / dispersion

    fallback = mean_abs_deviation(values)
    if fallback:
        # 1.2533 rescales mean absolute deviation to a standard-deviation
        # equivalent for normally distributed data.
        return (value - med) / (fallback * 1.2533)
    return None


def ewma(values: Sequence[float], alpha: float = 0.3) -> list[float]:
    """Exponentially weighted moving average."""
    out: list[float] = []
    current: float | None = None
    for v in values:
        if v is None:
            continue
        current = v if current is None else alpha * v + (1 - alpha) * current
        out.append(current)
    return out


def rolling_mean(values: Sequence[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    buffer: list[float] = []
    for v in values:
        buffer.append(v)
        if len(buffer) > window:
            buffer.pop(0)
        out.append(sum(buffer) / len(buffer) if buffer else None)
    return out


def rolling_stdev(values: Sequence[float], window: int) -> list[float | None]:
    out: list[float | None] = []
    buffer: list[float] = []
    for v in values:
        buffer.append(v)
        if len(buffer) > window:
            buffer.pop(0)
        out.append(stdev(buffer))
    return out


def linear_trend(values: Sequence[float]) -> float | None:
    """Least-squares slope per sample. Negative means declining."""
    clean = [v for v in values if v is not None]
    n = len(clean)
    if n < 3:
        return None
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(clean) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return None
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, clean, strict=True)) / denominator


def pct_change(before: float | None, after: float | None) -> float | None:
    """Percentage change from ``before`` to ``after``."""
    if before is None or after is None or before == 0:
        return None
    return (after - before) / abs(before) * 100.0


def split_halves(values: Sequence[float]) -> tuple[list[float], list[float]]:
    """Split a series into earlier/later halves for before-after comparison."""
    clean = [v for v in values if v is not None]
    if len(clean) < 4:
        return [], []
    mid = len(clean) // 2
    return clean[:mid], clean[mid:]


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or not denominator:
        return None
    return numerator / denominator
