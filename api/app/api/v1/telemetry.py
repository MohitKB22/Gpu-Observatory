"""GPU, system and overview telemetry endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.config import settings
from app.core.deps import DataSourceParam, DbSession, PaginationParam, require_scope
from app.core.errors import NotFoundError
from app.core.timerange import PRESET_RANGES, resolve_range
from app.models.enums import DataSource, Scope
from app.models.telemetry import GpuMetric, SystemMetric
from app.schemas.common import Page, PageMeta, TimeSeriesResponse
from app.schemas.telemetry import (
    GpuAvailability,
    GpuDetail,
    GpuMetricOut,
    GpuOut,
    GpuProcessOut,
    KpiValue,
    OverviewResponse,
    SystemMetricOut,
    SystemSnapshot,
    TelemetryIngest,
)
from app.services import alert_service, inference_service, telemetry_service

router = APIRouter(tags=["telemetry"])

ReadTelemetry = Depends(require_scope(Scope.TELEMETRY_READ))
WriteTelemetry = Depends(require_scope(Scope.TELEMETRY_WRITE))

RangeQuery = Annotated[
    str, Query(description=f"Preset window. One of: {', '.join(PRESET_RANGES)}.")
]


def _availability(data_source: str) -> GpuAvailability:
    """Report NVIDIA hardware availability honestly, never fabricating devices."""
    from app.realtime.workers import supervisor

    if data_source == DataSource.DEMO.value:
        return GpuAvailability(
            nvml_available=False,
            dcgm_available=False,
            gpu_count=settings.DEMO_GPU_COUNT,
            reason="demo_mode_synthetic_devices",
            demo_mode=True,
            driver_version="550.90.07 (simulated)",
            cuda_version="12.4",
        )

    nvml = supervisor.nvml
    dcgm = supervisor.dcgm
    nvml_status = nvml.status() if nvml else None
    dcgm_status = dcgm.status() if dcgm else None
    available = bool(nvml_status and nvml_status.available)
    reason = None
    if not available:
        reason = (
            nvml_status.reason
            if nvml_status
            else (
                "gpu_metrics_disabled"
                if not settings.GPU_METRICS_ENABLED
                else "collector_not_started"
            )
        )
    return GpuAvailability(
        nvml_available=available,
        dcgm_available=bool(dcgm_status and dcgm_status.available),
        gpu_count=int((nvml_status.detail.get("device_count") if nvml_status else 0) or 0),
        reason=reason,
        demo_mode=settings.DEMO_MODE,
        driver_version=nvml.driver_version if nvml else None,
        cuda_version=nvml.cuda_version if nvml else None,
    )


@router.get("/gpus", response_model=list[GpuOut], summary="List GPUs", dependencies=[ReadTelemetry])
async def list_gpus(session: DbSession, data_source: DataSourceParam) -> list[GpuOut]:
    gpus = await telemetry_service.list_gpus(session, data_source=data_source)
    return [GpuOut.model_validate(g) for g in gpus]


@router.get(
    "/gpus/availability",
    response_model=GpuAvailability,
    summary="NVIDIA hardware availability",
    dependencies=[ReadTelemetry],
)
async def gpu_availability(data_source: DataSourceParam) -> GpuAvailability:
    return _availability(data_source)


@router.get(
    "/gpus/{gpu_id}", response_model=GpuDetail, summary="GPU detail", dependencies=[ReadTelemetry]
)
async def get_gpu(gpu_id: str, session: DbSession, data_source: DataSourceParam) -> GpuDetail:
    gpu = await telemetry_service.get_gpu(session, gpu_id, data_source=data_source)
    if gpu is None:
        raise NotFoundError("GPU not found in this data source.", details={"gpu_id": gpu_id})
    latest = await telemetry_service.latest_gpu_metric(session, gpu_id, data_source=data_source)
    processes = await telemetry_service.latest_gpu_processes(
        session, gpu_id, data_source=data_source
    )
    return GpuDetail(
        gpu=GpuOut.model_validate(gpu),
        latest=GpuMetricOut.model_validate(latest) if latest else None,
        processes=[GpuProcessOut.model_validate(p) for p in processes],
        freshness=await telemetry_service.telemetry_freshness(session, data_source=data_source),
    )


@router.get(
    "/gpus/{gpu_id}/metrics",
    response_model=Page[GpuMetricOut],
    summary="Raw GPU samples",
    dependencies=[ReadTelemetry],
)
async def gpu_metrics(
    gpu_id: str,
    session: DbSession,
    data_source: DataSourceParam,
    pagination: PaginationParam,
    range: RangeQuery = "1h",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[GpuMetricOut]:
    gpu = await telemetry_service.get_gpu(session, gpu_id, data_source=data_source)
    if gpu is None:
        raise NotFoundError("GPU not found in this data source.", details={"gpu_id": gpu_id})

    time_range = resolve_range(range)
    base = select(GpuMetric).where(
        GpuMetric.gpu_id == gpu_id,
        GpuMetric.data_source == data_source,
        GpuMetric.recorded_at >= time_range.start,
        GpuMetric.recorded_at <= time_range.end,
    )
    total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    ordering = GpuMetric.recorded_at.desc() if order == "desc" else GpuMetric.recorded_at.asc()
    rows = list(
        (
            await session.execute(
                base.order_by(ordering).limit(pagination.limit).offset(pagination.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page[GpuMetricOut](
        items=[GpuMetricOut.model_validate(r) for r in rows],
        meta=PageMeta(
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(rows) < total,
        ),
    )


@router.get(
    "/gpus/series/timeseries",
    response_model=TimeSeriesResponse,
    summary="Bucketed GPU time-series",
    dependencies=[ReadTelemetry],
)
async def gpu_timeseries(
    session: DbSession,
    data_source: DataSourceParam,
    range: RangeQuery = "1h",
    start: datetime | None = None,
    end: datetime | None = None,
    metrics: Annotated[
        str, Query(description="Comma-separated GpuMetric fields.")
    ] = "utilization_pct",
    gpu_ids: Annotated[str | None, Query(description="Comma-separated GPU ids.")] = None,
) -> TimeSeriesResponse:
    time_range = resolve_range(range, start, end)
    allowed = {
        "utilization_pct",
        "memory_utilization_pct",
        "memory_used_mb",
        "memory_free_mb",
        "temperature_c",
        "power_w",
        "sm_clock_mhz",
        "memory_clock_mhz",
        "fan_speed_pct",
    }
    fields = [f.strip() for f in metrics.split(",") if f.strip() in allowed] or ["utilization_pct"]
    ids = [g.strip() for g in gpu_ids.split(",") if g.strip()] if gpu_ids else None

    series = await telemetry_service.gpu_series(
        session, time_range=time_range, data_source=data_source, gpu_ids=ids, fields=fields
    )
    return TimeSeriesResponse(
        range_label=time_range.label,
        start=time_range.start,
        end=time_range.end,
        bucket_seconds=time_range.bucket_seconds,
        data_source=data_source,
        series=series,
        freshness=await telemetry_service.telemetry_freshness(session, data_source=data_source),
    )


@router.get(
    "/system/metrics",
    response_model=SystemSnapshot,
    summary="Latest host metrics",
    dependencies=[ReadTelemetry],
)
async def system_metrics(session: DbSession, data_source: DataSourceParam) -> SystemSnapshot:
    latest = await telemetry_service.latest_system_metric(session, data_source=data_source)
    payload = SystemMetricOut.model_validate(latest) if latest is not None else None
    return SystemSnapshot(
        latest=payload,
        freshness=await telemetry_service.telemetry_freshness(session, data_source=data_source),
    )


@router.get(
    "/system/series",
    response_model=TimeSeriesResponse,
    summary="Bucketed host time-series",
    dependencies=[ReadTelemetry],
)
async def system_series(
    session: DbSession,
    data_source: DataSourceParam,
    range: RangeQuery = "1h",
    start: datetime | None = None,
    end: datetime | None = None,
    metrics: str = "cpu_utilization_pct,ram_utilization_pct",
) -> TimeSeriesResponse:
    time_range = resolve_range(range, start, end)
    allowed = {
        "cpu_utilization_pct",
        "ram_utilization_pct",
        "disk_utilization_pct",
        "load_avg_1m",
        "swap_used_mb",
        "net_sent_kb_s",
        "net_recv_kb_s",
        "process_count",
    }
    fields = [f.strip() for f in metrics.split(",") if f.strip() in allowed] or [
        "cpu_utilization_pct"
    ]
    series = await telemetry_service.system_series(
        session, time_range=time_range, data_source=data_source, fields=fields
    )
    return TimeSeriesResponse(
        range_label=time_range.label,
        start=time_range.start,
        end=time_range.end,
        bucket_seconds=time_range.bucket_seconds,
        data_source=data_source,
        series=series,
        freshness=await telemetry_service.telemetry_freshness(session, data_source=data_source),
    )


@router.post(
    "/telemetry/ingest",
    summary="Ingest telemetry from a remote agent",
    dependencies=[WriteTelemetry],
)
async def ingest(payload: TelemetryIngest, session: DbSession) -> dict:
    """Accept a batch from a telemetry agent running on a GPU node."""
    from app.collectors.base import GpuSample, SystemSample

    written = 0
    if payload.gpus:
        samples = []
        for item in payload.gpus:
            if not item.get("uuid"):
                continue
            samples.append(
                GpuSample(
                    uuid=str(item["uuid"]),
                    index=int(item.get("index", 0)),
                    recorded_at=payload.collected_at or datetime.now(timezone.utc),
                    utilization_pct=item.get("utilization_pct"),
                    memory_utilization_pct=item.get("memory_utilization_pct"),
                    memory_used_mb=item.get("memory_used_mb"),
                    memory_free_mb=item.get("memory_free_mb"),
                    memory_total_mb=item.get("memory_total_mb"),
                    temperature_c=item.get("temperature_c"),
                    power_w=item.get("power_w"),
                    power_limit_w=item.get("power_limit_w"),
                    sm_clock_mhz=item.get("sm_clock_mhz"),
                    memory_clock_mhz=item.get("memory_clock_mhz"),
                    fan_speed_pct=item.get("fan_speed_pct"),
                    throttle_reasons=list(item.get("throttle_reasons") or []),
                )
            )
        written = await telemetry_service.record_gpu_samples(
            session, samples, host=payload.host, data_source=payload.data_source
        )

    if payload.system:
        system = payload.system
        await telemetry_service.record_system_sample(
            session,
            SystemSample(
                recorded_at=payload.collected_at or datetime.now(timezone.utc),
                host=payload.host,
                cpu_utilization_pct=system.get("cpu_utilization_pct"),
                per_core_utilization=list(system.get("per_core_utilization") or []),
                core_count=system.get("core_count"),
                load_avg_1m=system.get("load_avg_1m"),
                ram_total_mb=system.get("ram_total_mb"),
                ram_used_mb=system.get("ram_used_mb"),
                ram_utilization_pct=system.get("ram_utilization_pct"),
                swap_used_mb=system.get("swap_used_mb"),
                disk_utilization_pct=system.get("disk_utilization_pct"),
                process_count=system.get("process_count"),
            ),
            data_source=payload.data_source,
        )

    return {"accepted": True, "gpu_samples": written, "host": payload.host}


@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Dashboard overview KPIs",
    dependencies=[ReadTelemetry],
)
async def overview(
    session: DbSession, data_source: DataSourceParam, range: RangeQuery = "1h"
) -> OverviewResponse:
    """Every KPI is computed from stored telemetry; nothing is hardcoded."""
    time_range = resolve_range(range)

    gpu_row = (
        await session.execute(
            select(
                func.avg(GpuMetric.utilization_pct),
                func.avg(GpuMetric.memory_utilization_pct),
                func.avg(GpuMetric.temperature_c),
                func.avg(GpuMetric.power_w),
            ).where(
                GpuMetric.data_source == data_source,
                GpuMetric.recorded_at >= time_range.start,
                GpuMetric.recorded_at <= time_range.end,
            )
        )
    ).one()
    cpu_avg = await session.scalar(
        select(func.avg(SystemMetric.cpu_utilization_pct)).where(
            SystemMetric.data_source == data_source,
            SystemMetric.recorded_at >= time_range.start,
            SystemMetric.recorded_at <= time_range.end,
        )
    )

    summary = await inference_service.summarize(
        session, time_range=time_range, data_source=data_source
    )

    cost_per_request = None
    try:
        from app.services.cost_service import summarize_cost

        cost = await summarize_cost(session, time_range=time_range, data_source=data_source)
        cost_per_request = cost.cost_per_request
    except Exception:
        cost_per_request = None

    def kpi(key, label, value, unit, healthy=None, estimate=False, digits=2) -> KpiValue:
        return KpiValue(
            key=key,
            label=label,
            value=round(float(value), digits) if value is not None else None,
            unit=unit,
            healthy=healthy,
            is_estimate=estimate,
        )

    gpu_util = float(gpu_row[0]) if gpu_row[0] is not None else None
    vram = float(gpu_row[1]) if gpu_row[1] is not None else None

    kpis = [
        kpi(
            "gpu_utilization",
            "GPU Utilisation",
            gpu_util,
            "%",
            healthy=(gpu_util >= 55) if gpu_util is not None else None,
        ),
        kpi(
            "vram_usage", "VRAM Usage", vram, "%", healthy=(vram < 92) if vram is not None else None
        ),
        kpi(
            "cpu_utilization",
            "CPU Utilisation",
            cpu_avg,
            "%",
            healthy=(float(cpu_avg) < 85) if cpu_avg is not None else None,
        ),
        kpi("p95_latency", "P95 Latency", summary.latency.p95, "ms"),
        kpi("throughput", "Throughput", summary.requests_per_second, "req/s", digits=3),
        kpi("tokens_per_second", "Tokens/sec", summary.tokens_per_second, "tok/s"),
        kpi("cost_per_request", "Cost/Request", cost_per_request, None, estimate=True, digits=6),
        kpi(
            "error_rate",
            "Error Rate",
            (summary.error_rate * 100) if summary.error_rate is not None else None,
            "%",
            healthy=(summary.error_rate < 0.02) if summary.error_rate is not None else None,
        ),
    ]

    return OverviewResponse(
        data_source=data_source,
        demo_mode=settings.DEMO_MODE,
        demo_scenario=settings.DEMO_SCENARIO if data_source == DataSource.DEMO.value else None,
        kpis=kpis,
        gpu_available=_availability(data_source),
        active_alert_count=await alert_service.count_active(session, data_source=data_source),
        latest_diagnosis_id=None,
        freshness=await telemetry_service.telemetry_freshness(session, data_source=data_source),
        generated_at=datetime.now(timezone.utc),
    )
