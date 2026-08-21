"""Evidence gathering for the diagnostics engine.

The context is assembled once from stored telemetry and handed to every rule.
Rules never issue their own queries, so a diagnosis is always a pure function
of an explicit, inspectable set of observations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timerange import TimeRange
from app.models.analytics import Alert
from app.models.enums import AlertState, DataSource
from app.models.inference import BatchMetric, Deployment, InferenceMetric
from app.models.telemetry import Gpu, GpuMetric, SystemMetric
from app.services.statistics import mean, pct_change, percentile, split_halves


@dataclass
class SeriesStats:
    """Summary of one signal over the analysis window."""

    values: list[float] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.values)

    @property
    def avg(self) -> float | None:
        return mean(self.values)

    @property
    def first_half_avg(self) -> float | None:
        first, _ = split_halves(self.values)
        return mean(first)

    @property
    def second_half_avg(self) -> float | None:
        _, second = split_halves(self.values)
        return mean(second)

    @property
    def change_pct(self) -> float | None:
        return pct_change(self.first_half_avg, self.second_half_avg)

    @property
    def latest(self) -> float | None:
        return self.values[-1] if self.values else None

    @property
    def peak(self) -> float | None:
        return max(self.values) if self.values else None

    @property
    def trough(self) -> float | None:
        return min(self.values) if self.values else None

    def p(self, q: float) -> float | None:
        return percentile(self.values, q)


@dataclass
class GpuContext:
    gpu_id: str
    label: str
    name: str
    utilization: SeriesStats
    vram_pct: SeriesStats
    vram_used_mb: SeriesStats
    temperature: SeriesStats
    power: SeriesStats
    sm_clock: SeriesStats
    power_limit_w: float | None = None
    max_clock_mhz: int | None = None
    total_memory_mb: float | None = None
    throttle_reasons: list[str] = field(default_factory=list)


@dataclass
class DiagnosticContext:
    """Everything the rules are allowed to reason about."""

    data_source: str
    time_range: TimeRange
    generated_at: datetime

    gpus: list[GpuContext] = field(default_factory=list)
    cpu: SeriesStats = field(default_factory=SeriesStats)
    ram: SeriesStats = field(default_factory=SeriesStats)
    swap_used: SeriesStats = field(default_factory=SeriesStats)

    latency_p95: SeriesStats = field(default_factory=SeriesStats)
    latency_p50: SeriesStats = field(default_factory=SeriesStats)
    latency_p99: SeriesStats = field(default_factory=SeriesStats)
    queue_latency: SeriesStats = field(default_factory=SeriesStats)
    throughput: SeriesStats = field(default_factory=SeriesStats)
    tokens_per_second: SeriesStats = field(default_factory=SeriesStats)
    error_rate: SeriesStats = field(default_factory=SeriesStats)
    batch_size: SeriesStats = field(default_factory=SeriesStats)
    concurrency: SeriesStats = field(default_factory=SeriesStats)

    queue_depth: SeriesStats = field(default_factory=SeriesStats)
    batch_efficiency: SeriesStats = field(default_factory=SeriesStats)
    configured_max_batch: int | None = None
    batch_window_ms: float | None = None

    request_count: int = 0
    active_alerts: int = 0
    has_inference_data: bool = False
    has_gpu_data: bool = False
    has_system_data: bool = False

    cost_per_hour: float | None = None
    cost_change_pct: float | None = None

    def gpu_by_id(self, gpu_id: str | None) -> GpuContext | None:
        if gpu_id is None:
            return self.gpus[0] if self.gpus else None
        return next((g for g in self.gpus if g.gpu_id == gpu_id), None)

    @property
    def avg_gpu_utilization(self) -> float | None:
        values = [g.utilization.avg for g in self.gpus if g.utilization.avg is not None]
        return mean(values) if values else None


async def build_context(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str = DataSource.PRODUCTION.value,
    entity_type: str | None = None,
    entity_id: str | None = None,
) -> DiagnosticContext:
    """Assemble the evidence bundle for a window."""
    context = DiagnosticContext(
        data_source=data_source,
        time_range=time_range,
        generated_at=datetime.now(timezone.utc),
    )

    gpu_stmt = select(Gpu).where(Gpu.data_source == data_source)
    if entity_type == "gpu" and entity_id:
        gpu_stmt = gpu_stmt.where(Gpu.id == entity_id)
    gpus = list((await session.execute(gpu_stmt.order_by(Gpu.index))).scalars().all())

    for gpu in gpus:
        rows = list(
            (
                await session.execute(
                    select(GpuMetric)
                    .where(
                        GpuMetric.gpu_id == gpu.id,
                        GpuMetric.data_source == data_source,
                        GpuMetric.recorded_at >= time_range.start,
                        GpuMetric.recorded_at <= time_range.end,
                    )
                    .order_by(GpuMetric.recorded_at)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            continue
        throttles: set[str] = set()
        for row in rows:
            if row.throttle_reasons:
                throttles.update(r for r in row.throttle_reasons.split(",") if r)

        context.gpus.append(
            GpuContext(
                gpu_id=gpu.id,
                label=f"GPU {gpu.index} · {gpu.name}",
                name=gpu.name,
                utilization=SeriesStats(
                    [r.utilization_pct for r in rows if r.utilization_pct is not None]
                ),
                vram_pct=SeriesStats(
                    [r.memory_utilization_pct for r in rows if r.memory_utilization_pct is not None]
                ),
                vram_used_mb=SeriesStats(
                    [r.memory_used_mb for r in rows if r.memory_used_mb is not None]
                ),
                temperature=SeriesStats(
                    [r.temperature_c for r in rows if r.temperature_c is not None]
                ),
                power=SeriesStats([r.power_w for r in rows if r.power_w is not None]),
                sm_clock=SeriesStats(
                    [float(r.sm_clock_mhz) for r in rows if r.sm_clock_mhz is not None]
                ),
                power_limit_w=gpu.power_limit_w,
                max_clock_mhz=gpu.max_clock_mhz,
                total_memory_mb=gpu.total_memory_mb,
                throttle_reasons=sorted(throttles),
            )
        )
    context.has_gpu_data = bool(context.gpus)

    system_rows = list(
        (
            await session.execute(
                select(SystemMetric)
                .where(
                    SystemMetric.data_source == data_source,
                    SystemMetric.recorded_at >= time_range.start,
                    SystemMetric.recorded_at <= time_range.end,
                )
                .order_by(SystemMetric.recorded_at)
            )
        )
        .scalars()
        .all()
    )
    if system_rows:
        context.cpu = SeriesStats(
            [r.cpu_utilization_pct for r in system_rows if r.cpu_utilization_pct is not None]
        )
        context.ram = SeriesStats(
            [r.ram_utilization_pct for r in system_rows if r.ram_utilization_pct is not None]
        )
        context.swap_used = SeriesStats(
            [r.swap_used_mb for r in system_rows if r.swap_used_mb is not None]
        )
        context.has_system_data = True

    inference_stmt = select(InferenceMetric).where(
        InferenceMetric.data_source == data_source,
        InferenceMetric.bucket_start >= time_range.start,
        InferenceMetric.bucket_start <= time_range.end,
    )
    if entity_type == "deployment" and entity_id:
        inference_stmt = inference_stmt.where(InferenceMetric.deployment_id == entity_id)
    inference_rows = list(
        (await session.execute(inference_stmt.order_by(InferenceMetric.bucket_start)))
        .scalars()
        .all()
    )
    if inference_rows:
        context.latency_p50 = SeriesStats(
            [r.p50_latency_ms for r in inference_rows if r.p50_latency_ms is not None]
        )
        context.latency_p95 = SeriesStats(
            [r.p95_latency_ms for r in inference_rows if r.p95_latency_ms is not None]
        )
        context.latency_p99 = SeriesStats(
            [r.p99_latency_ms for r in inference_rows if r.p99_latency_ms is not None]
        )
        context.queue_latency = SeriesStats(
            [r.avg_queue_latency_ms for r in inference_rows if r.avg_queue_latency_ms is not None]
        )
        context.throughput = SeriesStats(
            [r.requests_per_second for r in inference_rows if r.requests_per_second is not None]
        )
        context.tokens_per_second = SeriesStats(
            [r.tokens_per_second for r in inference_rows if r.tokens_per_second is not None]
        )
        context.error_rate = SeriesStats(
            [r.error_rate for r in inference_rows if r.error_rate is not None]
        )
        context.batch_size = SeriesStats(
            [r.avg_batch_size for r in inference_rows if r.avg_batch_size is not None]
        )
        context.concurrency = SeriesStats(
            [r.avg_concurrency for r in inference_rows if r.avg_concurrency is not None]
        )
        context.request_count = sum(r.request_count for r in inference_rows)
        context.has_inference_data = True

    batch_stmt = select(BatchMetric).where(
        BatchMetric.data_source == data_source,
        BatchMetric.bucket_start >= time_range.start,
        BatchMetric.bucket_start <= time_range.end,
    )
    if entity_type == "deployment" and entity_id:
        batch_stmt = batch_stmt.where(BatchMetric.deployment_id == entity_id)
    batch_rows = list(
        (await session.execute(batch_stmt.order_by(BatchMetric.bucket_start))).scalars().all()
    )
    if batch_rows:
        context.queue_depth = SeriesStats(
            [r.queue_depth for r in batch_rows if r.queue_depth is not None]
        )
        context.batch_efficiency = SeriesStats(
            [r.batch_efficiency for r in batch_rows if r.batch_efficiency is not None]
        )
        if not context.batch_size.values:
            context.batch_size = SeriesStats(
                [r.avg_batch_size for r in batch_rows if r.avg_batch_size is not None]
            )
        configured = [
            r.configured_max_batch_size for r in batch_rows if r.configured_max_batch_size
        ]
        context.configured_max_batch = max(configured) if configured else None

    deployment_stmt = select(Deployment).where(Deployment.data_source == data_source)
    if entity_type == "deployment" and entity_id:
        deployment_stmt = deployment_stmt.where(Deployment.id == entity_id)
    deployment = (await session.execute(deployment_stmt.limit(1))).scalar_one_or_none()
    if deployment:
        context.batch_window_ms = deployment.batch_window_ms
        if context.configured_max_batch is None:
            context.configured_max_batch = deployment.max_batch_size

    alert_rows = list(
        (
            await session.execute(
                select(Alert).where(
                    Alert.data_source == data_source,
                    Alert.state == AlertState.ACTIVE.value,
                )
            )
        )
        .scalars()
        .all()
    )
    context.active_alerts = len(alert_rows)

    return context


def recent_window(minutes: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)
