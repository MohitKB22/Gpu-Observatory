"""Inference request ingestion, aggregation and query logic."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import INFERENCE_LATENCY, INFERENCE_REQUESTS, INFERENCE_TOKENS
from app.core.timerange import TimeRange, floor_to_bucket
from app.models.inference import (
    BatchMetric,
    Deployment,
    InferenceMetric,
    InferenceRequest,
    MLModel,
)
from app.schemas.common import NamedSeries, SeriesPoint
from app.schemas.inference import (
    BatchAnalysis,
    BatchMetricOut,
    InferenceSummary,
    LatencyBreakdown,
    LatencyBucket,
    LatencyPercentiles,
)
from app.services.statistics import mean, percentile, safe_div

logger = get_logger(__name__)


async def record_requests(session: AsyncSession, payloads: list[dict], *, data_source: str) -> int:
    """Persist raw inference requests observed by the gateway."""
    if not payloads:
        return 0
    rows = []
    for payload in payloads:
        started = payload.get("started_at") or datetime.now(timezone.utc)
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        rows.append(
            InferenceRequest(
                deployment_id=payload.get("deployment_id"),
                model_id=payload.get("model_id"),
                gpu_id=payload.get("gpu_id"),
                started_at=started,
                data_source=data_source,
                total_latency_ms=float(payload["total_latency_ms"]),
                queue_latency_ms=payload.get("queue_latency_ms"),
                preprocess_latency_ms=payload.get("preprocess_latency_ms"),
                execution_latency_ms=payload.get("execution_latency_ms"),
                postprocess_latency_ms=payload.get("postprocess_latency_ms"),
                time_to_first_token_ms=payload.get("time_to_first_token_ms"),
                input_tokens=payload.get("input_tokens"),
                output_tokens=payload.get("output_tokens"),
                batch_size=payload.get("batch_size"),
                concurrency=payload.get("concurrency"),
                status_code=payload.get("status_code", 200),
                is_error=bool(payload.get("is_error", False)),
                error_type=payload.get("error_type"),
                client_id=payload.get("client_id"),
                trace_id=payload.get("trace_id"),
            )
        )
        deployment_label = payload.get("deployment_id") or "unknown"
        INFERENCE_REQUESTS.labels(
            deployment=deployment_label,
            status="error" if payload.get("is_error") else "ok",
            data_source=data_source,
        ).inc()
        INFERENCE_LATENCY.labels(deployment=deployment_label, data_source=data_source).observe(
            float(payload["total_latency_ms"]) / 1000.0
        )
        if payload.get("input_tokens"):
            INFERENCE_TOKENS.labels(
                deployment=deployment_label, direction="input", data_source=data_source
            ).inc(payload["input_tokens"])
        if payload.get("output_tokens"):
            INFERENCE_TOKENS.labels(
                deployment=deployment_label, direction="output", data_source=data_source
            ).inc(payload["output_tokens"])

    session.add_all(rows)
    await session.commit()
    return len(rows)


async def aggregate_bucket(
    session: AsyncSession,
    *,
    bucket_start: datetime,
    bucket_seconds: int,
    data_source: str,
    deployment_id: str | None = None,
) -> InferenceMetric | None:
    """Roll raw requests in a bucket into an InferenceMetric row.

    Dashboards read the aggregate table, never the raw request stream.
    """
    bucket_end = bucket_start.timestamp() + bucket_seconds
    stmt = select(InferenceRequest).where(
        InferenceRequest.data_source == data_source,
        InferenceRequest.started_at >= bucket_start,
        InferenceRequest.started_at < datetime.fromtimestamp(bucket_end, tz=timezone.utc),
    )
    if deployment_id:
        stmt = stmt.where(InferenceRequest.deployment_id == deployment_id)
    result = await session.execute(stmt)
    requests = list(result.scalars().all())
    if not requests:
        return None

    latencies = [r.total_latency_ms for r in requests]
    errors = [r for r in requests if r.is_error]
    input_tokens = sum(r.input_tokens or 0 for r in requests)
    output_tokens = sum(r.output_tokens or 0 for r in requests)
    batch_sizes = [r.batch_size for r in requests if r.batch_size]
    model_id = next((r.model_id for r in requests if r.model_id), None)

    existing = await session.execute(
        select(InferenceMetric).where(
            InferenceMetric.deployment_id == deployment_id,
            InferenceMetric.bucket_start == bucket_start,
            InferenceMetric.bucket_seconds == bucket_seconds,
            InferenceMetric.data_source == data_source,
        )
    )
    metric = existing.scalar_one_or_none()
    if metric is None:
        metric = InferenceMetric(
            deployment_id=deployment_id,
            model_id=model_id,
            bucket_start=bucket_start,
            bucket_seconds=bucket_seconds,
            data_source=data_source,
        )
        session.add(metric)

    metric.request_count = len(requests)
    metric.error_count = len(errors)
    metric.error_rate = len(errors) / len(requests)
    metric.requests_per_second = len(requests) / bucket_seconds
    metric.avg_latency_ms = mean(latencies)
    metric.min_latency_ms = min(latencies)
    metric.max_latency_ms = max(latencies)
    metric.p50_latency_ms = percentile(latencies, 50)
    metric.p90_latency_ms = percentile(latencies, 90)
    metric.p95_latency_ms = percentile(latencies, 95)
    metric.p99_latency_ms = percentile(latencies, 99)
    metric.avg_queue_latency_ms = mean(
        [r.queue_latency_ms for r in requests if r.queue_latency_ms is not None]
    )
    metric.avg_preprocess_latency_ms = mean(
        [r.preprocess_latency_ms for r in requests if r.preprocess_latency_ms is not None]
    )
    metric.avg_execution_latency_ms = mean(
        [r.execution_latency_ms for r in requests if r.execution_latency_ms is not None]
    )
    metric.avg_postprocess_latency_ms = mean(
        [r.postprocess_latency_ms for r in requests if r.postprocess_latency_ms is not None]
    )
    metric.total_input_tokens = input_tokens
    metric.total_output_tokens = output_tokens
    metric.input_tokens_per_second = input_tokens / bucket_seconds
    metric.output_tokens_per_second = output_tokens / bucket_seconds
    metric.tokens_per_second = (input_tokens + output_tokens) / bucket_seconds
    metric.avg_batch_size = mean(batch_sizes) if batch_sizes else None
    metric.max_batch_size = max(batch_sizes) if batch_sizes else None
    metric.avg_concurrency = mean([r.concurrency for r in requests if r.concurrency is not None])

    await session.commit()
    return metric


async def summarize(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str,
    deployment_id: str | None = None,
    model_id: str | None = None,
) -> InferenceSummary:
    """Summary statistics computed from stored aggregates, falling back to raw
    requests when no aggregate has been produced for the window yet."""
    stmt = select(InferenceMetric).where(
        InferenceMetric.data_source == data_source,
        InferenceMetric.bucket_start >= time_range.start,
        InferenceMetric.bucket_start <= time_range.end,
    )
    if deployment_id:
        stmt = stmt.where(InferenceMetric.deployment_id == deployment_id)
    if model_id:
        stmt = stmt.where(InferenceMetric.model_id == model_id)
    buckets = list((await session.execute(stmt)).scalars().all())

    summary = InferenceSummary(
        data_source=data_source,
        range_label=time_range.label,
        start=time_range.start,
        end=time_range.end,
    )

    if buckets:
        total_requests = sum(b.request_count for b in buckets)
        total_errors = sum(b.error_count for b in buckets)
        duration = max(1.0, float(time_range.duration_seconds))
        summary.request_count = total_requests
        summary.error_count = total_errors
        summary.error_rate = (total_errors / total_requests) if total_requests else None
        summary.requests_per_second = total_requests / duration
        summary.latency = LatencyPercentiles(
            avg=_weighted(buckets, "avg_latency_ms"),
            p50=_weighted(buckets, "p50_latency_ms"),
            p90=_weighted(buckets, "p90_latency_ms"),
            p95=_weighted(buckets, "p95_latency_ms"),
            p99=_weighted(buckets, "p99_latency_ms"),
            min=min(
                (b.min_latency_ms for b in buckets if b.min_latency_ms is not None), default=None
            ),
            max=max(
                (b.max_latency_ms for b in buckets if b.max_latency_ms is not None), default=None
            ),
        )
        summary.breakdown = LatencyBreakdown(
            queue_ms=_weighted(buckets, "avg_queue_latency_ms"),
            preprocess_ms=_weighted(buckets, "avg_preprocess_latency_ms"),
            execution_ms=_weighted(buckets, "avg_execution_latency_ms"),
            postprocess_ms=_weighted(buckets, "avg_postprocess_latency_ms"),
        )
        summary.total_input_tokens = sum(b.total_input_tokens for b in buckets)
        summary.total_output_tokens = sum(b.total_output_tokens for b in buckets)
        summary.input_tokens_per_second = summary.total_input_tokens / duration
        summary.output_tokens_per_second = summary.total_output_tokens / duration
        summary.tokens_per_second = (
            summary.total_input_tokens + summary.total_output_tokens
        ) / duration
        summary.avg_batch_size = _weighted(buckets, "avg_batch_size")
        summary.max_batch_size = max(
            (b.max_batch_size for b in buckets if b.max_batch_size is not None), default=None
        )
        summary.avg_concurrency = _weighted(buckets, "avg_concurrency")
        return summary

    return await _summarize_from_raw(
        session,
        time_range=time_range,
        data_source=data_source,
        deployment_id=deployment_id,
        model_id=model_id,
        summary=summary,
    )


async def _summarize_from_raw(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str,
    deployment_id: str | None,
    model_id: str | None,
    summary: InferenceSummary,
) -> InferenceSummary:
    stmt = select(InferenceRequest).where(
        InferenceRequest.data_source == data_source,
        InferenceRequest.started_at >= time_range.start,
        InferenceRequest.started_at <= time_range.end,
    )
    if deployment_id:
        stmt = stmt.where(InferenceRequest.deployment_id == deployment_id)
    if model_id:
        stmt = stmt.where(InferenceRequest.model_id == model_id)
    requests = list((await session.execute(stmt)).scalars().all())
    if not requests:
        return summary

    latencies = [r.total_latency_ms for r in requests]
    errors = [r for r in requests if r.is_error]
    duration = max(1.0, float(time_range.duration_seconds))
    batch_sizes = [r.batch_size for r in requests if r.batch_size]

    summary.request_count = len(requests)
    summary.error_count = len(errors)
    summary.error_rate = len(errors) / len(requests)
    summary.requests_per_second = len(requests) / duration
    summary.latency = LatencyPercentiles(
        avg=mean(latencies),
        p50=percentile(latencies, 50),
        p90=percentile(latencies, 90),
        p95=percentile(latencies, 95),
        p99=percentile(latencies, 99),
        min=min(latencies),
        max=max(latencies),
    )
    summary.breakdown = LatencyBreakdown(
        queue_ms=mean([r.queue_latency_ms for r in requests if r.queue_latency_ms is not None]),
        preprocess_ms=mean(
            [r.preprocess_latency_ms for r in requests if r.preprocess_latency_ms is not None]
        ),
        execution_ms=mean(
            [r.execution_latency_ms for r in requests if r.execution_latency_ms is not None]
        ),
        postprocess_ms=mean(
            [r.postprocess_latency_ms for r in requests if r.postprocess_latency_ms is not None]
        ),
    )
    summary.total_input_tokens = sum(r.input_tokens or 0 for r in requests)
    summary.total_output_tokens = sum(r.output_tokens or 0 for r in requests)
    summary.input_tokens_per_second = summary.total_input_tokens / duration
    summary.output_tokens_per_second = summary.total_output_tokens / duration
    summary.tokens_per_second = (
        summary.total_input_tokens + summary.total_output_tokens
    ) / duration
    summary.avg_batch_size = mean(batch_sizes) if batch_sizes else None
    summary.max_batch_size = max(batch_sizes) if batch_sizes else None
    summary.avg_concurrency = mean([r.concurrency for r in requests if r.concurrency is not None])
    return summary


async def latency_distribution(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str,
    deployment_id: str | None = None,
    bins: int = 24,
) -> list[LatencyBucket]:
    """Histogram of observed latencies for the distribution chart."""
    stmt = select(InferenceRequest.total_latency_ms).where(
        InferenceRequest.data_source == data_source,
        InferenceRequest.started_at >= time_range.start,
        InferenceRequest.started_at <= time_range.end,
    )
    if deployment_id:
        stmt = stmt.where(InferenceRequest.deployment_id == deployment_id)
    values = [float(v) for v in (await session.execute(stmt)).scalars().all()]
    if not values:
        return []

    low = min(values)
    # Clip the axis at P99 so a single outlier cannot flatten the histogram.
    high = percentile(values, 99) or max(values)
    if high <= low:
        high = low + 1.0
    width = (high - low) / bins

    counts = [0] * bins
    overflow = 0
    for value in values:
        if value > high:
            overflow += 1
            continue
        index = min(bins - 1, int((value - low) / width))
        counts[index] += 1

    buckets = [
        LatencyBucket(
            lower_ms=round(low + i * width, 2), upper_ms=round(low + (i + 1) * width, 2), count=c
        )
        for i, c in enumerate(counts)
    ]
    if overflow:
        buckets.append(LatencyBucket(lower_ms=round(high, 2), upper_ms=None, count=overflow))
    return buckets


async def inference_series(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str,
    fields: list[str] | None = None,
    deployment_id: str | None = None,
) -> list[NamedSeries]:
    fields = fields or ["requests_per_second", "p95_latency_ms", "tokens_per_second"]
    stmt = select(InferenceMetric).where(
        InferenceMetric.data_source == data_source,
        InferenceMetric.bucket_start >= time_range.start,
        InferenceMetric.bucket_start <= time_range.end,
    )
    if deployment_id:
        stmt = stmt.where(InferenceMetric.deployment_id == deployment_id)
    buckets = list(
        (await session.execute(stmt.order_by(InferenceMetric.bucket_start))).scalars().all()
    )

    accumulator: dict[str, dict[str, list[float]]] = {}
    for bucket in buckets:
        key = floor_to_bucket(bucket.bucket_start, time_range.bucket_seconds).isoformat()
        per_field = accumulator.setdefault(key, {})
        for field_name in fields:
            value = getattr(bucket, field_name, None)
            if value is not None:
                per_field.setdefault(field_name, []).append(float(value))

    series_map: dict[str, NamedSeries] = {}
    units = {
        "requests_per_second": "req/s",
        "p50_latency_ms": "ms",
        "p90_latency_ms": "ms",
        "p95_latency_ms": "ms",
        "p99_latency_ms": "ms",
        "avg_latency_ms": "ms",
        "tokens_per_second": "tok/s",
        "error_rate": "ratio",
        "avg_batch_size": "requests",
    }
    for key in sorted(accumulator):
        timestamp = datetime.fromisoformat(key)
        for field_name, values in accumulator[key].items():
            if field_name not in series_map:
                series_map[field_name] = NamedSeries(
                    name=field_name, unit=units.get(field_name), points=[]
                )
            series_map[field_name].points.append(
                SeriesPoint(timestamp=timestamp, value=sum(values) / len(values))
            )
    return list(series_map.values())


async def analyse_batching(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str,
    deployment_id: str | None = None,
) -> BatchAnalysis:
    """Batching health, including explicit under/over-batching detection."""
    stmt = select(BatchMetric).where(
        BatchMetric.data_source == data_source,
        BatchMetric.bucket_start >= time_range.start,
        BatchMetric.bucket_start <= time_range.end,
    )
    if deployment_id:
        stmt = stmt.where(BatchMetric.deployment_id == deployment_id)
    buckets = list((await session.execute(stmt.order_by(BatchMetric.bucket_start))).scalars().all())

    analysis = BatchAnalysis(data_source=data_source)
    if not buckets:
        return analysis

    analysis.avg_batch_size = mean([b.avg_batch_size for b in buckets if b.avg_batch_size])
    analysis.max_batch_size = max(
        (b.max_batch_size for b in buckets if b.max_batch_size), default=None
    )
    configured = [b.configured_max_batch_size for b in buckets if b.configured_max_batch_size]
    analysis.configured_max_batch_size = max(configured) if configured else None
    analysis.avg_queue_depth = mean([b.queue_depth for b in buckets if b.queue_depth is not None])
    analysis.avg_batch_formation_ms = mean(
        [b.batch_formation_ms for b in buckets if b.batch_formation_ms is not None]
    )
    analysis.avg_gpu_utilization = mean(
        [b.gpu_utilization_pct for b in buckets if b.gpu_utilization_pct is not None]
    )
    analysis.throughput_rps = mean(
        [b.throughput_rps for b in buckets if b.throughput_rps is not None]
    )
    analysis.batch_efficiency = safe_div(
        analysis.avg_batch_size, analysis.configured_max_batch_size
    )

    if analysis.batch_efficiency is not None:
        # Under-batching: batches far below capacity while the GPU is idle.
        analysis.under_batching_detected = (
            analysis.batch_efficiency < 0.35 and (analysis.avg_gpu_utilization or 100) < 60
        )
        # Over-batching: batches at the ceiling with queueing behind them.
        analysis.over_batching_detected = (
            analysis.batch_efficiency > 0.95 and (analysis.avg_queue_depth or 0) > 8
        )
        analysis.headroom_pct = round((1 - analysis.batch_efficiency) * 100, 2)

    analysis.buckets = [BatchMetricOut.model_validate(b) for b in buckets[-240:]]
    return analysis


async def record_batch_metric(
    session: AsyncSession,
    *,
    bucket_start: datetime,
    bucket_seconds: int,
    data_source: str,
    deployment_id: str | None,
    snapshot: dict,
) -> BatchMetric:
    existing = await session.execute(
        select(BatchMetric).where(
            BatchMetric.deployment_id == deployment_id,
            BatchMetric.bucket_start == bucket_start,
            BatchMetric.bucket_seconds == bucket_seconds,
            BatchMetric.data_source == data_source,
        )
    )
    metric = existing.scalar_one_or_none()
    if metric is None:
        metric = BatchMetric(
            deployment_id=deployment_id,
            bucket_start=bucket_start,
            bucket_seconds=bucket_seconds,
            data_source=data_source,
        )
        session.add(metric)
    for key, value in snapshot.items():
        if hasattr(metric, key):
            setattr(metric, key, value)
    await session.commit()
    return metric


async def count_requests(session: AsyncSession, *, data_source: str, since: datetime) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(InferenceRequest)
            .where(
                InferenceRequest.data_source == data_source,
                InferenceRequest.started_at >= since,
            )
        )
        or 0
    )


def _weighted(buckets: list[InferenceMetric], field: str) -> float | None:
    """Request-count-weighted average across buckets.

    A plain mean would let a bucket with three requests count as much as one
    with three thousand.
    """
    total_weight = 0
    total = 0.0
    for bucket in buckets:
        value = getattr(bucket, field, None)
        if value is None or not bucket.request_count:
            continue
        total += float(value) * bucket.request_count
        total_weight += bucket.request_count
    return (total / total_weight) if total_weight else None


async def resolve_default_deployment(
    session: AsyncSession, *, data_source: str
) -> Deployment | None:
    result = await session.execute(
        select(Deployment)
        .where(Deployment.data_source == data_source)
        .order_by(Deployment.created_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_models(session: AsyncSession, *, data_source: str) -> list[MLModel]:
    result = await session.execute(
        select(MLModel).where(MLModel.data_source == data_source).order_by(MLModel.name)
    )
    return list(result.scalars().all())
