"""Cost observability.

Every figure produced here is an ESTIMATE derived from a configurable pricing
profile. Cloud list prices change constantly and vary by contract, so no price
is hardcoded as universal truth -- the default profile is seeded from
environment configuration and is fully editable at runtime.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.core.timerange import TimeRange
from app.models.analytics import PricingProfile
from app.models.enums import DataSource, PricingKind
from app.models.inference import InferenceMetric
from app.models.telemetry import Gpu, GpuMetric
from app.schemas.analytics import CostBreakdownItem, CostSummary

logger = get_logger(__name__)

ESTIMATE_NOTE = (
    "All cost figures are estimates calculated from the active pricing profile. "
    "They are not billing data and should not be used for invoicing."
)


async def get_default_pricing(session: AsyncSession) -> PricingProfile | None:
    result = await session.execute(
        select(PricingProfile).where(PricingProfile.is_default.is_(True)).limit(1)
    )
    profile = result.scalar_one_or_none()
    if profile is not None:
        return profile
    result = await session.execute(
        select(PricingProfile).order_by(PricingProfile.created_at).limit(1)
    )
    return result.scalar_one_or_none()


async def ensure_default_pricing(session: AsyncSession) -> PricingProfile:
    """Seed a default pricing profile from configuration if none exists."""
    existing = await get_default_pricing(session)
    if existing is not None:
        return existing
    profile = PricingProfile(
        name="Default (from configuration)",
        kind=PricingKind.CLOUD_HOURLY.value,
        cost_per_gpu_hour=settings.COST_PER_GPU_HOUR,
        currency=settings.COST_CURRENCY,
        energy_cost_per_kwh=settings.ENERGY_COST_PER_KWH,
        is_default=True,
        is_estimate=True,
        notes=(
            "Seeded from COST_PER_GPU_HOUR. Replace with the rate your "
            "organisation actually pays before relying on these figures."
        ),
        effective_from=datetime.now(timezone.utc),
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    logger.info("default_pricing_seeded", rate=profile.cost_per_gpu_hour)
    return profile


async def _gpu_hours(
    session: AsyncSession, *, time_range: TimeRange, data_source: str
) -> tuple[float, dict[str, tuple[str, float, float]]]:
    """Compute GPU-hours from actual sample coverage.

    Each sample represents one collection interval of device time; summing
    intervals is more honest than assuming the device ran for the whole window.
    Also returns per-GPU (label, hours, avg_utilisation).
    """
    rows = list(
        (
            await session.execute(
                select(
                    GpuMetric.gpu_id,
                    func.count(GpuMetric.id),
                    func.avg(GpuMetric.utilization_pct),
                    func.avg(GpuMetric.power_w),
                )
                .where(
                    GpuMetric.data_source == data_source,
                    GpuMetric.recorded_at >= time_range.start,
                    GpuMetric.recorded_at <= time_range.end,
                )
                .group_by(GpuMetric.gpu_id)
            )
        ).all()
    )
    if not rows:
        return 0.0, {}

    interval = (
        settings.DEMO_INTERVAL_SECONDS
        if data_source == DataSource.DEMO.value
        else settings.TELEMETRY_INTERVAL_SECONDS
    )
    gpu_ids = [r[0] for r in rows]
    name_rows = (await session.execute(select(Gpu.id, Gpu.name).where(Gpu.id.in_(gpu_ids)))).all()
    names: dict[str, str] = {row[0]: row[1] for row in name_rows}

    total_hours = 0.0
    per_gpu: dict[str, tuple[str, float, float]] = {}
    window_hours = time_range.duration_seconds / 3600.0

    for gpu_id, count, avg_util, _avg_power in rows:
        # Cap at the wall-clock window: a device cannot run longer than the window.
        hours = min(window_hours, (count * interval) / 3600.0)
        total_hours += hours
        per_gpu[gpu_id] = (names.get(gpu_id, gpu_id), hours, float(avg_util or 0.0))

    return total_hours, per_gpu


async def summarize_cost(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str,
    pricing: PricingProfile | None = None,
) -> CostSummary:
    profile = pricing or await get_default_pricing(session)
    rate = profile.cost_per_gpu_hour if profile else settings.COST_PER_GPU_HOUR
    currency = profile.currency if profile else settings.COST_CURRENCY
    profile_name = profile.name if profile else "Configuration default"

    gpu_hours, per_gpu = await _gpu_hours(session, time_range=time_range, data_source=data_source)
    total_cost = gpu_hours * rate

    totals = (
        await session.execute(
            select(
                func.coalesce(func.sum(InferenceMetric.request_count), 0),
                func.coalesce(func.sum(InferenceMetric.total_input_tokens), 0),
                func.coalesce(func.sum(InferenceMetric.total_output_tokens), 0),
            ).where(
                InferenceMetric.data_source == data_source,
                InferenceMetric.bucket_start >= time_range.start,
                InferenceMetric.bucket_start <= time_range.end,
            )
        )
    ).one()
    request_count = int(totals[0] or 0)
    total_tokens = int((totals[1] or 0) + (totals[2] or 0))

    energy_cost: float | None = None
    if profile and profile.energy_cost_per_kwh:
        avg_power = await session.scalar(
            select(func.avg(GpuMetric.power_w)).where(
                GpuMetric.data_source == data_source,
                GpuMetric.recorded_at >= time_range.start,
                GpuMetric.recorded_at <= time_range.end,
            )
        )
        if avg_power:
            kwh = (float(avg_power) / 1000.0) * gpu_hours
            energy_cost = round(kwh * profile.energy_cost_per_kwh, 4)

    window_hours = max(time_range.duration_seconds / 3600.0, 1e-9)
    hourly_cost = total_cost / window_hours

    breakdown = [
        CostBreakdownItem(
            label=label,
            entity_id=gpu_id,
            gpu_hours=round(hours, 4),
            cost=round(hours * rate, 4),
            share_pct=round(hours / gpu_hours * 100, 2) if gpu_hours else None,
        )
        for gpu_id, (label, hours, _util) in sorted(
            per_gpu.items(), key=lambda kv: kv[1][1], reverse=True
        )
    ]

    notes = [ESTIMATE_NOTE]
    if profile and profile.kind == PricingKind.ON_PREM_AMORTIZED.value:
        notes.append("On-premises rate is amortised capital cost, excluding facilities overhead.")
    if not gpu_hours:
        notes.append("No GPU telemetry in this window, so GPU-hours are zero.")

    return CostSummary(
        data_source=data_source,
        currency=currency,
        range_label=time_range.label,
        start=time_range.start,
        end=time_range.end,
        pricing_profile=profile_name,
        cost_per_gpu_hour=rate,
        is_estimate=True,
        gpu_hours=round(gpu_hours, 4),
        total_cost=round(total_cost, 4),
        energy_cost=energy_cost,
        request_count=request_count,
        total_tokens=total_tokens,
        cost_per_request=round(total_cost / request_count, 6) if request_count else None,
        cost_per_1k_tokens=round(total_cost / total_tokens * 1_000, 6) if total_tokens else None,
        cost_per_1m_tokens=(
            round(total_cost / total_tokens * 1_000_000, 4) if total_tokens else None
        ),
        daily_cost=round(hourly_cost * 24, 4),
        projected_monthly_cost=round(hourly_cost * 24 * 30, 2),
        breakdown=breakdown,
        notes=notes,
    )


async def window_cost_trend(
    session: AsyncSession, *, time_range: TimeRange, data_source: str
) -> tuple[float | None, float | None]:
    """Hourly cost for this window and the immediately preceding one."""
    from app.core.timerange import TimeRange as TR

    current = await summarize_cost(session, time_range=time_range, data_source=data_source)
    window_hours = max(time_range.duration_seconds / 3600.0, 1e-9)
    current_hourly = current.total_cost / window_hours

    span = timedelta(seconds=time_range.duration_seconds)
    previous_range = TR(
        start=time_range.start - span,
        end=time_range.start,
        bucket_seconds=time_range.bucket_seconds,
        label="previous",
    )
    previous = await summarize_cost(session, time_range=previous_range, data_source=data_source)
    previous_hourly = previous.total_cost / window_hours
    return current_hourly, (previous_hourly or None)


async def cost_per_model(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str,
    model_id: str,
    gpu_hours_share: float | None = None,
) -> tuple[float | None, float | None]:
    """Estimate (cost_per_request, cost_per_1m_tokens) for one model."""
    profile = await get_default_pricing(session)
    rate = profile.cost_per_gpu_hour if profile else settings.COST_PER_GPU_HOUR

    row = (
        await session.execute(
            select(
                func.coalesce(func.sum(InferenceMetric.request_count), 0),
                func.coalesce(func.sum(InferenceMetric.total_input_tokens), 0),
                func.coalesce(func.sum(InferenceMetric.total_output_tokens), 0),
            ).where(
                InferenceMetric.data_source == data_source,
                InferenceMetric.model_id == model_id,
                InferenceMetric.bucket_start >= time_range.start,
                InferenceMetric.bucket_start <= time_range.end,
            )
        )
    ).one()
    requests = int(row[0] or 0)
    tokens = int((row[1] or 0) + (row[2] or 0))
    if not requests:
        return None, None

    if gpu_hours_share is None:
        gpu_hours_share, _ = await _gpu_hours(
            session, time_range=time_range, data_source=data_source
        )
    cost = gpu_hours_share * rate
    return (
        round(cost / requests, 6),
        round(cost / tokens * 1_000_000, 4) if tokens else None,
    )
