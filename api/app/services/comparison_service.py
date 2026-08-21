"""Model performance rollups and side-by-side comparison.

Recommendations are computed arithmetically from stored metrics. Nothing here
consults an LLM, so the numbers cannot drift from the measurements.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.timerange import TimeRange
from app.models.inference import BatchMetric, Deployment, InferenceMetric, MLModel
from app.models.telemetry import GpuMetric
from app.schemas.inference import ComparisonDelta, ComparisonResponse, ModelPerformance
from app.services.cost_service import cost_per_model
from app.services.statistics import pct_change

logger = get_logger(__name__)

# metric key -> (label, unit, lower_is_better)
COMPARISON_METRICS: list[tuple[str, str, str | None, bool]] = [
    ("avg_latency_ms", "Average latency", "ms", True),
    ("p95_latency_ms", "P95 latency", "ms", True),
    ("p99_latency_ms", "P99 latency", "ms", True),
    ("throughput_rps", "Throughput", "req/s", False),
    ("tokens_per_second", "Token throughput", "tok/s", False),
    ("avg_batch_size", "Average batch size", "requests", False),
    ("batch_efficiency", "Batch efficiency", "ratio", False),
    ("avg_gpu_utilization", "GPU utilisation", "%", False),
    ("avg_vram_used_mb", "VRAM used", "MB", True),
    ("error_rate", "Error rate", "ratio", True),
    ("cost_per_request", "Cost per request", None, True),
    ("cost_per_1m_tokens", "Cost per 1M tokens", None, True),
]

# Weights used to rank candidates. Throughput and cost dominate, with latency
# and reliability as meaningful secondary factors.
_SCORE_WEIGHTS = {
    "throughput_rps": 0.28,
    "cost_per_1m_tokens": 0.24,
    "p95_latency_ms": 0.20,
    "tokens_per_second": 0.14,
    "error_rate": 0.14,
}


async def model_performance(
    session: AsyncSession, *, model: MLModel, time_range: TimeRange, data_source: str
) -> ModelPerformance:
    """Aggregate every stored signal for one model over the window."""
    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(InferenceMetric.request_count), 0),
                func.coalesce(func.sum(InferenceMetric.error_count), 0),
                func.avg(InferenceMetric.avg_latency_ms),
                func.avg(InferenceMetric.p95_latency_ms),
                func.avg(InferenceMetric.p99_latency_ms),
                func.avg(InferenceMetric.requests_per_second),
                func.avg(InferenceMetric.tokens_per_second),
                func.avg(InferenceMetric.avg_batch_size),
                func.max(InferenceMetric.max_batch_size),
            ).where(
                InferenceMetric.model_id == model.id,
                InferenceMetric.data_source == data_source,
                InferenceMetric.bucket_start >= time_range.start,
                InferenceMetric.bucket_start <= time_range.end,
            )
        )
    ).one()

    request_count = int(row[0] or 0)
    error_count = int(row[1] or 0)

    performance = ModelPerformance(
        model_id=model.id,
        model_name=model.name,
        version=model.version,
        quantization=model.quantization,
        framework=model.framework,
        request_count=request_count,
        avg_latency_ms=_round(row[2]),
        p95_latency_ms=_round(row[3]),
        p99_latency_ms=_round(row[4]),
        throughput_rps=_round(row[5], 3),
        tokens_per_second=_round(row[6], 2),
        avg_batch_size=_round(row[7], 2),
        error_rate=round(error_count / request_count, 5) if request_count else None,
        has_data=request_count > 0,
    )

    configured_max = model.max_batch_size
    if performance.avg_batch_size and configured_max:
        performance.batch_efficiency = round(performance.avg_batch_size / configured_max, 4)

    # GPU signals, scoped to the GPUs this model is actually deployed on.
    gpu_ids = list(
        (
            await session.execute(
                select(Deployment.gpu_id).where(
                    Deployment.model_id == model.id,
                    Deployment.data_source == data_source,
                    Deployment.gpu_id.is_not(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if gpu_ids:
        gpu_row = (
            await session.execute(
                select(
                    func.avg(GpuMetric.utilization_pct),
                    func.avg(GpuMetric.memory_used_mb),
                ).where(
                    GpuMetric.gpu_id.in_(gpu_ids),
                    GpuMetric.data_source == data_source,
                    GpuMetric.recorded_at >= time_range.start,
                    GpuMetric.recorded_at <= time_range.end,
                )
            )
        ).one()
        performance.avg_gpu_utilization = _round(gpu_row[0], 2)
        performance.avg_vram_used_mb = _round(gpu_row[1], 1)

    if performance.batch_efficiency is None:
        batch_row = (
            await session.execute(
                select(func.avg(BatchMetric.batch_efficiency)).where(
                    BatchMetric.data_source == data_source,
                    BatchMetric.bucket_start >= time_range.start,
                    BatchMetric.bucket_start <= time_range.end,
                )
            )
        ).scalar()
        performance.batch_efficiency = _round(batch_row, 4)

    if request_count:
        cost_request, cost_tokens = await cost_per_model(
            session, time_range=time_range, data_source=data_source, model_id=model.id
        )
        performance.cost_per_request = cost_request
        performance.cost_per_1m_tokens = cost_tokens

    return performance


async def compare(
    session: AsyncSession, *, model_ids: list[str], time_range: TimeRange, data_source: str
) -> ComparisonResponse:
    """Compare two or more models and produce a computed recommendation."""
    unique_ids = list(dict.fromkeys(model_ids))
    if len(unique_ids) < 2:
        raise ValidationError("At least two distinct models are required for a comparison.")
    if len(unique_ids) > 6:
        raise ValidationError("A maximum of six models can be compared at once.")

    models = list(
        (
            await session.execute(
                select(MLModel).where(
                    MLModel.id.in_(unique_ids), MLModel.data_source == data_source
                )
            )
        )
        .scalars()
        .all()
    )
    found = {m.id for m in models}
    missing = [i for i in unique_ids if i not in found]
    if missing:
        raise NotFoundError(
            "One or more models were not found in this data source.",
            details={"missing_model_ids": missing, "data_source": data_source},
        )

    ordered = sorted(models, key=lambda m: unique_ids.index(m.id))
    performances = [
        await model_performance(session, model=m, time_range=time_range, data_source=data_source)
        for m in ordered
    ]

    baseline = performances[0]
    deltas: list[ComparisonDelta] = []
    for key, label, unit, lower_better in COMPARISON_METRICS:
        base_value = getattr(baseline, key, None)
        for candidate in performances[1:]:
            candidate_value = getattr(candidate, key, None)
            change = pct_change(base_value, candidate_value)
            better: str | None
            if base_value is None or candidate_value is None:
                better = "unknown"
            elif abs(change or 0) < 1.0:
                better = "tie"
            elif (candidate_value < base_value) == lower_better:
                better = "candidate"
            else:
                better = "baseline"
            deltas.append(
                ComparisonDelta(
                    metric=key,
                    label=f"{label} · {candidate.model_name}",
                    baseline_value=base_value,
                    candidate_value=candidate_value,
                    delta_pct=round(change, 2) if change is not None else None,
                    better=better,
                    unit=unit,
                    lower_is_better=lower_better,
                )
            )

    recommendation, recommended_id, confidence, caveats = _recommend(performances)

    return ComparisonResponse(
        data_source=data_source,
        range_label=time_range.label,
        models=performances,
        deltas=deltas,
        recommendation=recommendation,
        recommended_model_id=recommended_id,
        confidence=confidence,
        caveats=caveats,
        generated_at=datetime.now(timezone.utc),
    )


def _recommend(
    performances: list[ModelPerformance],
) -> tuple[str | None, str | None, float | None, list[str]]:
    """Rank models on a weighted, normalised score over comparable metrics."""
    caveats: list[str] = []
    with_data = [p for p in performances if p.has_data]
    if len(with_data) < 2:
        missing = [p.model_name for p in performances if not p.has_data]
        caveats.append(
            "Not enough measured data to make a recommendation."
            + (f" No telemetry for: {', '.join(missing)}." if missing else "")
        )
        return None, None, None, caveats

    low_volume = [p.model_name for p in with_data if p.request_count < 100]
    if low_volume:
        caveats.append(
            f"Low sample volume for {', '.join(low_volume)} (fewer than 100 requests); "
            "treat the comparison as indicative only."
        )

    scores: dict[str, float] = {p.model_id: 0.0 for p in with_data}
    used_weight = 0.0

    for metric, weight in _SCORE_WEIGHTS.items():
        values = {
            p.model_id: getattr(p, metric)
            for p in with_data
            if getattr(p, metric, None) is not None
        }
        if len(values) < 2:
            continue
        lower_better = next(lb for key, _label, _u, lb in COMPARISON_METRICS if key == metric)
        low, high = min(values.values()), max(values.values())
        span = high - low
        used_weight += weight
        for model_id, value in values.items():
            if span == 0:
                normalised = 0.5
            else:
                normalised = (value - low) / span
                if lower_better:
                    normalised = 1.0 - normalised
            scores[model_id] += normalised * weight

    if used_weight == 0:
        caveats.append("No overlapping metrics were available to score these models.")
        return None, None, None, caveats

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    winner_id, winner_score = ranked[0]
    runner_id, runner_score = ranked[1]
    winner = next(p for p in with_data if p.model_id == winner_id)
    runner = next(p for p in with_data if p.model_id == runner_id)

    # Describe the win in the metrics that actually differ.
    phrases: list[str] = []
    for metric, label, _unit, lower_better in COMPARISON_METRICS:
        if metric not in _SCORE_WEIGHTS:
            continue
        win_value = getattr(winner, metric, None)
        run_value = getattr(runner, metric, None)
        change = pct_change(run_value, win_value)
        if change is None or abs(change) < 2:
            continue
        improved = (change < 0) if lower_better else (change > 0)
        phrases.append(
            f"{abs(change):.0f}% {'lower' if change < 0 else 'higher'} {label.lower()}"
            + ("" if improved else " (worse)")
        )

    margin = (winner_score - runner_score) / max(used_weight, 1e-9)
    confidence = round(min(0.95, 0.5 + margin * 1.6), 2)

    if not phrases:
        recommendation = (
            f"{winner.model_name} and {runner.model_name} perform comparably on the "
            "measured metrics; no clear winner."
        )
        return recommendation, winner_id, round(0.5, 2), caveats

    recommendation = (
        f"{winner.model_name} is the stronger choice over {runner.model_name}: "
        + ", ".join(phrases[:3])
        + ", measured over the selected window."
    )
    if margin < 0.05:
        caveats.append("The margin between the top two models is narrow.")
    return recommendation, winner_id, confidence, caveats


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(float(value), digits) if value is not None else None
