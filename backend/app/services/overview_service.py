"""The Overview page in one response: KPIs with comparison, trend, models and system health."""

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ModelStatus
from app.monitoring.sampler import SystemSampler
from app.schemas.common import DataSource, TimeWindow
from app.schemas.overview import ModelHealthCounts, OverviewModel, OverviewResponse, SystemHealth
from app.services.analytics_service import (
    AnalyticsQuery,
    fetch_model_comparison,
    fetch_summary,
    fetch_timeseries,
)
from app.services.infrastructure_service import check_database
from app.services.model_service import list_models


async def build_overview(
    session: AsyncSession, window: TimeWindow, data_source: DataSource, sampler: SystemSampler
) -> OverviewResponse:
    query = AnalyticsQuery.for_window(window, data_source)
    summary, scope = await fetch_summary(session, query)
    previous_summary, _ = await fetch_summary(session, query.previous_period())
    timeseries = await fetch_timeseries(session, query, window.bucket_seconds)
    stats_by_model = {row.model_id: row.stats for row in await fetch_model_comparison(session, query)}
    models = await list_models(session)

    overview_models = []
    for model in models:
        stats = stats_by_model.get(model.id)
        overview_models.append(
            OverviewModel(
                id=model.id,
                name=model.name,
                provider=model.provider,
                is_demo=model.is_demo,
                is_enabled=model.is_enabled,
                status=model.status,
                last_checked_at=model.last_checked_at,
                requests=stats.total_requests if stats else 0,
                p95_ms=stats.latency.p95_ms if stats else None,
                error_rate=stats.error_rate if stats else None,
            )
        )
    overview_models.sort(key=lambda item: item.requests, reverse=True)

    database = await check_database(session)
    sample = sampler.latest()
    gpu = sampler.latest_gpu_report
    return OverviewResponse(
        window=window,
        generated_at=datetime.now(UTC),
        bucket_seconds=window.bucket_seconds,
        scope=scope,
        summary=summary,
        previous_summary=previous_summary,
        timeseries=timeseries,
        models=overview_models,
        system=SystemHealth(
            database_ok=database.ok,
            database_latency_ms=database.latency_ms,
            cpu_percent=sample.cpu_percent,
            memory_percent=sample.memory_percent,
            gpu_available=bool(gpu and gpu.available),
            gpu_utilization_percent=sample.gpu_utilization_percent,
            gpu_unavailable_reason=gpu.unavailable_reason if gpu else "Not sampled yet.",
            models=ModelHealthCounts(
                total=len(models),
                enabled=sum(1 for m in models if m.is_enabled),
                healthy=sum(1 for m in models if m.status == ModelStatus.HEALTHY),
                unhealthy=sum(1 for m in models if m.status == ModelStatus.UNHEALTHY),
                unknown=sum(1 for m in models if m.status == ModelStatus.UNKNOWN),
            ),
        ),
    )
