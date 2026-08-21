"""Persistence and query layer for GPU and system telemetry."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collectors.base import GpuDeviceInfo, GpuSample, SystemSample
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import (
    GPU_MEMORY_USED,
    GPU_POWER,
    GPU_TEMPERATURE,
    GPU_UTILIZATION,
    TELEMETRY_SAMPLES,
)
from app.core.timerange import TimeRange, floor_to_bucket
from app.models.enums import DataSource
from app.models.telemetry import Gpu, GpuMetric, GpuProcess, SystemMetric
from app.schemas.common import DataFreshness, NamedSeries, SeriesPoint

logger = get_logger(__name__)


async def upsert_gpu(
    session: AsyncSession,
    device: GpuDeviceInfo,
    *,
    host: str = "localhost",
    data_source: str = DataSource.PRODUCTION.value,
) -> Gpu:
    """Register or refresh a GPU device record."""
    result = await session.execute(
        select(Gpu).where(Gpu.uuid == device.uuid, Gpu.data_source == data_source)
    )
    gpu = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if gpu is None:
        gpu = Gpu(uuid=device.uuid, index=device.index, name=device.name, data_source=data_source)
        session.add(gpu)

    gpu.index = device.index
    gpu.name = device.name
    gpu.host = host
    gpu.driver_version = device.driver_version
    gpu.cuda_version = device.cuda_version
    gpu.vbios_version = device.vbios_version
    gpu.serial = device.serial
    gpu.total_memory_mb = device.total_memory_mb
    gpu.power_limit_w = device.power_limit_w
    gpu.max_clock_mhz = device.max_clock_mhz
    gpu.max_memory_clock_mhz = device.max_memory_clock_mhz
    gpu.compute_capability = device.compute_capability
    gpu.pcie_gen = device.pcie_gen
    gpu.pcie_width = device.pcie_width
    gpu.is_available = True
    gpu.last_seen_at = now

    await session.flush()
    return gpu


async def record_gpu_samples(
    session: AsyncSession,
    samples: list[GpuSample],
    *,
    host: str = "localhost",
    data_source: str = DataSource.PRODUCTION.value,
) -> int:
    """Persist a batch of GPU samples plus their process tables."""
    if not samples:
        return 0

    uuids = [s.uuid for s in samples]
    result = await session.execute(
        select(Gpu).where(Gpu.uuid.in_(uuids), Gpu.data_source == data_source)
    )
    by_uuid = {gpu.uuid: gpu for gpu in result.scalars().all()}

    rows: list[GpuMetric] = []
    process_rows: list[GpuProcess] = []

    for sample in samples:
        gpu = by_uuid.get(sample.uuid)
        if gpu is None:
            # Auto-register a device we have not seen before.
            gpu = await upsert_gpu(
                session,
                GpuDeviceInfo(
                    uuid=sample.uuid,
                    index=sample.index,
                    name=f"NVIDIA GPU {sample.index}",
                    total_memory_mb=sample.memory_total_mb,
                    power_limit_w=sample.power_limit_w,
                ),
                host=host,
                data_source=data_source,
            )
            by_uuid[sample.uuid] = gpu
        else:
            gpu.last_seen_at = sample.recorded_at

        rows.append(
            GpuMetric(
                gpu_id=gpu.id,
                recorded_at=sample.recorded_at,
                data_source=data_source,
                utilization_pct=sample.utilization_pct,
                memory_utilization_pct=sample.memory_utilization_pct,
                memory_used_mb=sample.memory_used_mb,
                memory_free_mb=sample.memory_free_mb,
                memory_total_mb=sample.memory_total_mb,
                temperature_c=sample.temperature_c,
                power_w=sample.power_w,
                power_limit_w=sample.power_limit_w,
                sm_clock_mhz=sample.sm_clock_mhz,
                memory_clock_mhz=sample.memory_clock_mhz,
                fan_speed_pct=sample.fan_speed_pct,
                pcie_tx_kb_s=sample.pcie_tx_kb_s,
                pcie_rx_kb_s=sample.pcie_rx_kb_s,
                throttle_reasons=",".join(sample.throttle_reasons) or None,
                ecc_errors=sample.ecc_errors,
            )
        )

        for proc in sample.processes:
            process_rows.append(
                GpuProcess(
                    gpu_id=gpu.id,
                    recorded_at=sample.recorded_at,
                    pid=proc.pid,
                    process_name=proc.process_name,
                    used_memory_mb=proc.used_memory_mb,
                    sm_utilization_pct=proc.sm_utilization_pct,
                    workload_label=proc.workload_label,
                    data_source=data_source,
                )
            )

        labels = {
            "gpu_uuid": sample.uuid,
            "gpu_index": str(sample.index),
            "data_source": data_source,
        }
        if sample.utilization_pct is not None:
            GPU_UTILIZATION.labels(**labels, gpu_name=gpu.name).set(sample.utilization_pct)
        if sample.memory_used_mb is not None:
            GPU_MEMORY_USED.labels(**labels).set(sample.memory_used_mb)
        if sample.temperature_c is not None:
            GPU_TEMPERATURE.labels(**labels).set(sample.temperature_c)
        if sample.power_w is not None:
            GPU_POWER.labels(**labels).set(sample.power_w)

    session.add_all(rows)
    if process_rows:
        # Replace the previous process snapshot rather than accumulating rows.
        await session.execute(
            delete(GpuProcess).where(
                GpuProcess.gpu_id.in_([g.id for g in by_uuid.values()]),
                GpuProcess.data_source == data_source,
            )
        )
        session.add_all(process_rows)

    await session.commit()
    TELEMETRY_SAMPLES.labels(kind="gpu", data_source=data_source).inc(len(rows))
    return len(rows)


async def record_system_sample(
    session: AsyncSession,
    sample: SystemSample,
    *,
    data_source: str = DataSource.PRODUCTION.value,
) -> SystemMetric:
    row = SystemMetric(
        host=sample.host,
        recorded_at=sample.recorded_at,
        data_source=data_source,
        cpu_utilization_pct=sample.cpu_utilization_pct,
        per_core_utilization=(
            json.dumps(sample.per_core_utilization) if sample.per_core_utilization else None
        ),
        core_count=sample.core_count,
        load_avg_1m=sample.load_avg_1m,
        load_avg_5m=sample.load_avg_5m,
        load_avg_15m=sample.load_avg_15m,
        ram_total_mb=sample.ram_total_mb,
        ram_used_mb=sample.ram_used_mb,
        ram_utilization_pct=sample.ram_utilization_pct,
        swap_total_mb=sample.swap_total_mb,
        swap_used_mb=sample.swap_used_mb,
        disk_total_gb=sample.disk_total_gb,
        disk_used_gb=sample.disk_used_gb,
        disk_utilization_pct=sample.disk_utilization_pct,
        net_sent_kb_s=sample.net_sent_kb_s,
        net_recv_kb_s=sample.net_recv_kb_s,
        process_count=sample.process_count,
    )
    session.add(row)
    await session.commit()
    TELEMETRY_SAMPLES.labels(kind="system", data_source=data_source).inc()
    return row


# ------------------------------------------------------------------ reads ---
async def list_gpus(
    session: AsyncSession, *, data_source: str, include_unavailable: bool = True
) -> list[Gpu]:
    stmt = select(Gpu).where(Gpu.data_source == data_source)
    if not include_unavailable:
        stmt = stmt.where(Gpu.is_available.is_(True))
    result = await session.execute(stmt.order_by(Gpu.index))
    return list(result.scalars().all())


async def get_gpu(session: AsyncSession, gpu_id: str, *, data_source: str) -> Gpu | None:
    result = await session.execute(
        select(Gpu).where(Gpu.id == gpu_id, Gpu.data_source == data_source)
    )
    return result.scalar_one_or_none()


async def latest_gpu_metric(
    session: AsyncSession, gpu_id: str, *, data_source: str
) -> GpuMetric | None:
    result = await session.execute(
        select(GpuMetric)
        .where(GpuMetric.gpu_id == gpu_id, GpuMetric.data_source == data_source)
        .order_by(GpuMetric.recorded_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def latest_gpu_processes(
    session: AsyncSession, gpu_id: str, *, data_source: str, limit: int = 50
) -> list[GpuProcess]:
    result = await session.execute(
        select(GpuProcess)
        .where(GpuProcess.gpu_id == gpu_id, GpuProcess.data_source == data_source)
        .order_by(GpuProcess.recorded_at.desc(), GpuProcess.used_memory_mb.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def latest_system_metric(
    session: AsyncSession, *, data_source: str, host: str | None = None
) -> SystemMetric | None:
    stmt = select(SystemMetric).where(SystemMetric.data_source == data_source)
    if host:
        stmt = stmt.where(SystemMetric.host == host)
    result = await session.execute(stmt.order_by(SystemMetric.recorded_at.desc()).limit(1))
    return result.scalar_one_or_none()


async def gpu_series(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str,
    gpu_ids: list[str] | None = None,
    fields: list[str] | None = None,
) -> list[NamedSeries]:
    """Bucketed GPU time-series.

    Aggregation happens in SQL where possible; the bucket key is computed in
    Python for portability across PostgreSQL and SQLite, which keeps a single
    code path for both the production database and the test-suite.
    """
    fields = fields or ["utilization_pct"]
    stmt = (
        select(GpuMetric, Gpu.name, Gpu.index)
        .join(Gpu, Gpu.id == GpuMetric.gpu_id)
        .where(
            GpuMetric.data_source == data_source,
            GpuMetric.recorded_at >= time_range.start,
            GpuMetric.recorded_at <= time_range.end,
        )
    )
    if gpu_ids:
        stmt = stmt.where(GpuMetric.gpu_id.in_(gpu_ids))
    stmt = stmt.order_by(GpuMetric.recorded_at)

    result = await session.execute(stmt)
    rows = result.all()

    # bucket -> gpu_id -> field -> [values]
    accumulator: dict[str, dict[str, dict[str, list[float]]]] = {}
    labels: dict[str, str] = {}

    for metric, gpu_name, gpu_index in rows:
        bucket = floor_to_bucket(metric.recorded_at, time_range.bucket_seconds)
        key = bucket.isoformat()
        labels[metric.gpu_id] = f"GPU {gpu_index} · {gpu_name}"
        per_gpu = accumulator.setdefault(key, {}).setdefault(metric.gpu_id, {})
        for field_name in fields:
            value = getattr(metric, field_name, None)
            if value is not None:
                per_gpu.setdefault(field_name, []).append(float(value))

    series_map: dict[tuple[str, str], NamedSeries] = {}
    for bucket_key in sorted(accumulator):
        timestamp = datetime.fromisoformat(bucket_key)
        for gpu_id, per_field in accumulator[bucket_key].items():
            for field_name, values in per_field.items():
                identity = (gpu_id, field_name)
                if identity not in series_map:
                    series_map[identity] = NamedSeries(
                        name=f"{labels.get(gpu_id, gpu_id)} · {field_name}",
                        unit=_unit_for(field_name),
                        entity_id=gpu_id,
                        entity_label=labels.get(gpu_id),
                        points=[],
                    )
                series_map[identity].points.append(
                    SeriesPoint(timestamp=timestamp, value=sum(values) / len(values))
                )

    return list(series_map.values())


async def system_series(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str,
    fields: list[str] | None = None,
) -> list[NamedSeries]:
    fields = fields or ["cpu_utilization_pct", "ram_utilization_pct"]
    result = await session.execute(
        select(SystemMetric)
        .where(
            SystemMetric.data_source == data_source,
            SystemMetric.recorded_at >= time_range.start,
            SystemMetric.recorded_at <= time_range.end,
        )
        .order_by(SystemMetric.recorded_at)
    )
    rows = list(result.scalars().all())

    accumulator: dict[str, dict[str, list[float]]] = {}
    for metric in rows:
        bucket = floor_to_bucket(metric.recorded_at, time_range.bucket_seconds).isoformat()
        per_field = accumulator.setdefault(bucket, {})
        for field_name in fields:
            value = getattr(metric, field_name, None)
            if value is not None:
                per_field.setdefault(field_name, []).append(float(value))

    series_map: dict[str, NamedSeries] = {}
    for bucket_key in sorted(accumulator):
        timestamp = datetime.fromisoformat(bucket_key)
        for field_name, values in accumulator[bucket_key].items():
            if field_name not in series_map:
                series_map[field_name] = NamedSeries(
                    name=field_name, unit=_unit_for(field_name), points=[]
                )
            series_map[field_name].points.append(
                SeriesPoint(timestamp=timestamp, value=sum(values) / len(values))
            )
    return list(series_map.values())


async def gpu_values(
    session: AsyncSession,
    *,
    field: str,
    since: datetime,
    data_source: str,
    gpu_id: str | None = None,
) -> list[float]:
    """Raw values for a single field -- used by anomaly detection and rules."""
    column = getattr(GpuMetric, field, None)
    if column is None:
        return []
    stmt = select(column).where(
        GpuMetric.data_source == data_source,
        GpuMetric.recorded_at >= since,
        column.is_not(None),
    )
    if gpu_id:
        stmt = stmt.where(GpuMetric.gpu_id == gpu_id)
    result = await session.execute(stmt.order_by(GpuMetric.recorded_at))
    return [float(v) for v in result.scalars().all()]


async def telemetry_freshness(session: AsyncSession, *, data_source: str) -> DataFreshness:
    """How recent is the newest telemetry sample?"""
    newest = await session.scalar(
        select(func.max(GpuMetric.recorded_at)).where(GpuMetric.data_source == data_source)
    )
    if newest is None:
        newest = await session.scalar(
            select(func.max(SystemMetric.recorded_at)).where(
                SystemMetric.data_source == data_source
            )
        )
    expected = (
        settings.DEMO_INTERVAL_SECONDS
        if data_source == DataSource.DEMO.value
        else settings.TELEMETRY_INTERVAL_SECONDS
    )
    if newest is None:
        return DataFreshness(expected_interval_seconds=expected, is_stale=True)

    if newest.tzinfo is None:
        newest = newest.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - newest).total_seconds()
    return DataFreshness(
        last_sample_at=newest,
        age_seconds=round(age, 2),
        # Three missed intervals (floor 30s) is the staleness threshold.
        is_stale=age > max(30.0, expected * 3),
        expected_interval_seconds=expected,
    )


async def purge_expired(session: AsyncSession) -> dict[str, int]:
    """Apply retention policy. Returns rows deleted per table."""
    now = datetime.now(timezone.utc)
    raw_cutoff = now - timedelta(days=settings.RETENTION_RAW_DAYS)
    aggregate_cutoff = now - timedelta(days=settings.RETENTION_AGGREGATED_DAYS)

    from app.models.analytics import Anomaly
    from app.models.inference import BatchMetric, InferenceMetric, InferenceRequest

    deleted: dict[str, int] = {}
    raw_targets = [
        ("gpu_metrics", GpuMetric, GpuMetric.recorded_at),
        ("system_metrics", SystemMetric, SystemMetric.recorded_at),
        ("gpu_processes", GpuProcess, GpuProcess.recorded_at),
        ("inference_requests", InferenceRequest, InferenceRequest.started_at),
    ]
    for name, model, column in raw_targets:
        result = await session.execute(delete(model).where(column < raw_cutoff))
        deleted[name] = result.rowcount or 0

    aggregate_targets = [
        ("inference_metrics", InferenceMetric, InferenceMetric.bucket_start),
        ("batch_metrics", BatchMetric, BatchMetric.bucket_start),
        ("anomalies", Anomaly, Anomaly.detected_at),
    ]
    for name, model, column in aggregate_targets:
        result = await session.execute(delete(model).where(column < aggregate_cutoff))
        deleted[name] = result.rowcount or 0

    await session.commit()
    return deleted


_UNITS = {
    "utilization_pct": "%",
    "memory_utilization_pct": "%",
    "memory_used_mb": "MB",
    "memory_free_mb": "MB",
    "temperature_c": "°C",
    "power_w": "W",
    "sm_clock_mhz": "MHz",
    "memory_clock_mhz": "MHz",
    "fan_speed_pct": "%",
    "cpu_utilization_pct": "%",
    "ram_utilization_pct": "%",
    "disk_utilization_pct": "%",
}


def _unit_for(field: str) -> str | None:
    return _UNITS.get(field)
