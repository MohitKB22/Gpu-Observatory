"""Statistical anomaly detection over telemetry series.

Uses robust statistics by default: a median/MAD z-score is not masked by the
very outlier it is trying to find, unlike a mean/stdev z-score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import ANOMALIES_DETECTED
from app.models.analytics import Anomaly
from app.models.enums import AnomalyMethod, DataSource, MetricKind, Severity
from app.models.inference import InferenceMetric
from app.models.telemetry import GpuMetric, SystemMetric
from app.services.statistics import (
    ewma,
    mean,
    percentile,
    robust_zscore,
    stdev,
    zscore,
)

logger = get_logger(__name__)


@dataclass
class AnomalyCandidate:
    metric_kind: str
    method: str
    observed_value: float
    expected_value: float | None
    score: float | None
    threshold: float | None
    severity: str
    description: str
    entity_type: str | None = None
    entity_id: str | None = None
    entity_label: str | None = None
    sample_count: int | None = None
    deviation: float | None = None


def _severity_for(score: float, threshold: float) -> str:
    ratio = abs(score) / threshold if threshold else 0.0
    if ratio >= 2.5:
        return Severity.CRITICAL.value
    if ratio >= 1.8:
        return Severity.HIGH.value
    if ratio >= 1.3:
        return Severity.MEDIUM.value
    return Severity.LOW.value


def detect_zscore(
    values: list[float],
    *,
    metric_kind: str,
    threshold: float | None = None,
    robust: bool = True,
    higher_is_worse: bool = True,
    label: str | None = None,
) -> AnomalyCandidate | None:
    """Flag the most recent point if it deviates beyond ``threshold`` sigmas."""
    threshold = threshold or settings.ANOMALY_ZSCORE_THRESHOLD
    if len(values) < settings.ANOMALY_MIN_SAMPLES:
        return None

    history, latest = values[:-1], values[-1]
    score = robust_zscore(latest, history) if robust else zscore(latest, history)
    if score is None:
        # Fall back to the other estimator when dispersion is degenerate.
        score = zscore(latest, history) if robust else robust_zscore(latest, history)
    if score is None or abs(score) < threshold:
        return None
    if higher_is_worse and score < 0:
        return None

    expected = mean(history)
    direction = "above" if score > 0 else "below"
    return AnomalyCandidate(
        metric_kind=metric_kind,
        method=AnomalyMethod.ZSCORE.value,
        observed_value=round(latest, 4),
        expected_value=round(expected, 4) if expected is not None else None,
        score=round(score, 3),
        threshold=threshold,
        severity=_severity_for(score, threshold),
        deviation=round(latest - expected, 4) if expected is not None else None,
        sample_count=len(values),
        description=(
            f"{label or metric_kind} is {abs(score):.1f}σ {direction} its recent "
            f"baseline ({latest:.2f} observed vs {expected:.2f} expected)."
        ),
    )


def detect_ewma(
    values: list[float],
    *,
    metric_kind: str,
    alpha: float | None = None,
    tolerance: float = 3.0,
    label: str | None = None,
) -> AnomalyCandidate | None:
    """Flag divergence between the latest point and its EWMA baseline."""
    alpha = alpha or settings.ANOMALY_EWMA_ALPHA
    if len(values) < settings.ANOMALY_MIN_SAMPLES:
        return None

    smoothed = ewma(values[:-1], alpha)
    if not smoothed:
        return None
    baseline = smoothed[-1]
    residuals = [v - s for v, s in zip(values[:-1], smoothed, strict=True)]
    dispersion = stdev(residuals)
    if not dispersion:
        return None

    latest = values[-1]
    deviation = latest - baseline
    if abs(deviation) < tolerance * dispersion:
        return None

    score = deviation / dispersion
    return AnomalyCandidate(
        metric_kind=metric_kind,
        method=AnomalyMethod.EWMA.value,
        observed_value=round(latest, 4),
        expected_value=round(baseline, 4),
        score=round(score, 3),
        threshold=tolerance,
        severity=_severity_for(score, tolerance),
        deviation=round(deviation, 4),
        sample_count=len(values),
        description=(
            f"{label or metric_kind} diverged from its EWMA baseline "
            f"({latest:.2f} observed vs {baseline:.2f} smoothed)."
        ),
    )


def detect_percentile(
    values: list[float],
    *,
    metric_kind: str,
    upper_q: float = 99.0,
    label: str | None = None,
) -> AnomalyCandidate | None:
    """Flag the latest point when it exceeds a high percentile of its history."""
    if len(values) < settings.ANOMALY_MIN_SAMPLES:
        return None
    history, latest = values[:-1], values[-1]
    ceiling = percentile(history, upper_q)
    if ceiling is None or latest <= ceiling:
        return None
    baseline = percentile(history, 50) or ceiling
    if baseline == 0:
        return None
    excess = (latest - ceiling) / abs(baseline)
    if excess < 0.1:
        return None
    return AnomalyCandidate(
        metric_kind=metric_kind,
        method=AnomalyMethod.PERCENTILE.value,
        observed_value=round(latest, 4),
        expected_value=round(ceiling, 4),
        score=round(excess, 3),
        threshold=upper_q,
        severity=_severity_for(excess * 3, 3.0),
        deviation=round(latest - ceiling, 4),
        sample_count=len(values),
        description=(
            f"{label or metric_kind} exceeded its P{upper_q:.0f} historical "
            f"ceiling ({latest:.2f} observed vs {ceiling:.2f})."
        ),
    )


async def scan(
    session: AsyncSession,
    *,
    data_source: str = DataSource.PRODUCTION.value,
    window_minutes: int = 60,
    persist: bool = True,
) -> list[Anomaly]:
    """Scan every monitored signal and persist newly detected anomalies."""
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    candidates: list[AnomalyCandidate] = []

    # ---- per-GPU signals ----
    gpu_rows = list(
        (
            await session.execute(
                select(GpuMetric)
                .where(GpuMetric.data_source == data_source, GpuMetric.recorded_at >= since)
                .order_by(GpuMetric.recorded_at)
            )
        )
        .scalars()
        .all()
    )
    by_gpu: dict[str, list[GpuMetric]] = {}
    for row in gpu_rows:
        by_gpu.setdefault(row.gpu_id, []).append(row)

    gpu_signals = [
        ("utilization_pct", MetricKind.GPU_UTILIZATION.value, "GPU utilisation", False),
        ("memory_utilization_pct", MetricKind.VRAM_UTILIZATION.value, "VRAM utilisation", True),
        ("temperature_c", MetricKind.TEMPERATURE.value, "GPU temperature", True),
        ("power_w", MetricKind.POWER.value, "GPU power draw", True),
    ]
    for gpu_id, rows in by_gpu.items():
        for field, kind, label, higher_bad in gpu_signals:
            values = [getattr(r, field) for r in rows if getattr(r, field) is not None]
            found = detect_zscore(
                values, metric_kind=kind, higher_is_worse=higher_bad, label=label
            ) or detect_ewma(values, metric_kind=kind, label=label)
            if found:
                found.entity_type, found.entity_id = "gpu", gpu_id
                candidates.append(found)

    # ---- inference signals ----
    inference_rows = list(
        (
            await session.execute(
                select(InferenceMetric)
                .where(
                    InferenceMetric.data_source == data_source,
                    InferenceMetric.bucket_start >= since,
                )
                .order_by(InferenceMetric.bucket_start)
            )
        )
        .scalars()
        .all()
    )
    inference_signals = [
        ("p95_latency_ms", MetricKind.LATENCY_P95.value, "P95 latency", True),
        ("requests_per_second", MetricKind.THROUGHPUT.value, "Throughput", False),
        ("tokens_per_second", MetricKind.TOKENS_PER_SECOND.value, "Token throughput", False),
        ("error_rate", MetricKind.ERROR_RATE.value, "Error rate", True),
        ("avg_batch_size", MetricKind.BATCH_SIZE.value, "Average batch size", False),
    ]
    for field, kind, label, higher_bad in inference_signals:
        values = [getattr(r, field) for r in inference_rows if getattr(r, field) is not None]
        found = detect_zscore(values, metric_kind=kind, higher_is_worse=higher_bad, label=label)
        if found is None and higher_bad:
            found = detect_percentile(values, metric_kind=kind, label=label)
        if found:
            found.entity_type = "deployment"
            candidates.append(found)

    # ---- host signals ----
    system_rows = list(
        (
            await session.execute(
                select(SystemMetric)
                .where(SystemMetric.data_source == data_source, SystemMetric.recorded_at >= since)
                .order_by(SystemMetric.recorded_at)
            )
        )
        .scalars()
        .all()
    )
    cpu_values = [r.cpu_utilization_pct for r in system_rows if r.cpu_utilization_pct is not None]
    found = detect_zscore(
        cpu_values, metric_kind=MetricKind.CPU_UTILIZATION.value, label="CPU utilisation"
    )
    if found:
        found.entity_type = "host"
        candidates.append(found)

    if not persist:
        return [_to_model(c, data_source) for c in candidates]

    stored: list[Anomaly] = []
    now = datetime.now(timezone.utc)
    for candidate in candidates:
        # Suppress duplicates for the same signal within a short cooldown.
        recent = await session.execute(
            select(Anomaly)
            .where(
                Anomaly.metric_kind == candidate.metric_kind,
                Anomaly.entity_id == candidate.entity_id,
                Anomaly.data_source == data_source,
                Anomaly.detected_at >= now - timedelta(minutes=5),
            )
            .limit(1)
        )
        if recent.scalar_one_or_none() is not None:
            continue
        anomaly = _to_model(candidate, data_source)
        session.add(anomaly)
        stored.append(anomaly)
        ANOMALIES_DETECTED.labels(
            metric_kind=candidate.metric_kind, severity=candidate.severity
        ).inc()

    if stored:
        await session.commit()
        logger.info("anomalies_detected", count=len(stored), data_source=data_source)
    return stored


def _to_model(candidate: AnomalyCandidate, data_source: str) -> Anomaly:
    return Anomaly(
        detected_at=datetime.now(timezone.utc),
        metric_kind=candidate.metric_kind,
        method=candidate.method,
        severity=candidate.severity,
        data_source=data_source,
        entity_type=candidate.entity_type,
        entity_id=candidate.entity_id,
        entity_label=candidate.entity_label,
        observed_value=candidate.observed_value,
        expected_value=candidate.expected_value,
        deviation=candidate.deviation,
        score=candidate.score,
        threshold=candidate.threshold,
        sample_count=candidate.sample_count,
        description=candidate.description,
    )
