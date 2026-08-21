"""Threshold alert evaluation and lifecycle management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.errors import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.core.metrics import ALERTS_ACTIVE, ALERTS_FIRED
from app.core.timerange import resolve_range
from app.models.analytics import Alert, AlertRule
from app.models.enums import AlertCondition, AlertState, DataSource, Severity
from app.models.inference import InferenceMetric
from app.models.telemetry import Gpu, GpuMetric
from app.schemas.analytics import AlertSummary

logger = get_logger(__name__)

DEFAULT_RULES = [
    (
        "GPU utilisation below 40%",
        AlertCondition.GPU_UTILIZATION_BELOW.value,
        40.0,
        Severity.MEDIUM.value,
    ),
    ("VRAM above 92%", AlertCondition.VRAM_ABOVE.value, 92.0, Severity.HIGH.value),
    (
        "GPU temperature above 83°C",
        AlertCondition.TEMPERATURE_ABOVE.value,
        83.0,
        Severity.HIGH.value,
    ),
    (
        "P95 latency above 500 ms",
        AlertCondition.P95_LATENCY_ABOVE.value,
        500.0,
        Severity.MEDIUM.value,
    ),
    ("Throughput below 5 req/s", AlertCondition.THROUGHPUT_BELOW.value, 5.0, Severity.MEDIUM.value),
    ("Error rate above 5%", AlertCondition.ERROR_RATE_ABOVE.value, 0.05, Severity.HIGH.value),
    ("Estimated hourly cost above 50", AlertCondition.COST_ABOVE.value, 50.0, Severity.LOW.value),
]


async def ensure_default_rules(session: AsyncSession, *, data_source: str) -> int:
    """Seed the standard rule set for a namespace if it has none."""
    existing = await session.scalar(
        select(func.count()).select_from(AlertRule).where(AlertRule.data_source == data_source)
    )
    if existing:
        return 0
    for name, condition, threshold, severity in DEFAULT_RULES:
        session.add(
            AlertRule(
                name=name,
                condition=condition,
                threshold=threshold,
                severity=severity,
                data_source=data_source,
                description="Seeded default rule. Adjust or disable to suit your environment.",
            )
        )
    await session.commit()
    logger.info("default_alert_rules_seeded", count=len(DEFAULT_RULES), data_source=data_source)
    return len(DEFAULT_RULES)


async def _current_values(
    session: AsyncSession, *, data_source: str, window_minutes: int = 5
) -> dict[str, tuple[float, str | None, str | None]]:
    """Latest observed value per condition: (value, entity_id, entity_label)."""
    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    values: dict[str, tuple[float, str | None, str | None]] = {}

    gpu_rows = list(
        (
            await session.execute(
                select(
                    GpuMetric.gpu_id,
                    func.avg(GpuMetric.utilization_pct),
                    func.max(GpuMetric.memory_utilization_pct),
                    func.max(GpuMetric.temperature_c),
                    func.max(GpuMetric.power_w),
                )
                .where(GpuMetric.data_source == data_source, GpuMetric.recorded_at >= since)
                .group_by(GpuMetric.gpu_id)
            )
        ).all()
    )
    if gpu_rows:
        name_rows = (
            await session.execute(
                select(Gpu.id, Gpu.name).where(Gpu.id.in_([r[0] for r in gpu_rows]))
            )
        ).all()
        names: dict[str, str] = {row[0]: row[1] for row in name_rows}
        # Alert on the worst device for each condition.
        worst_util = min(gpu_rows, key=lambda r: r[1] if r[1] is not None else 1e9)
        if worst_util[1] is not None:
            values[AlertCondition.GPU_UTILIZATION_BELOW.value] = (
                float(worst_util[1]),
                worst_util[0],
                names.get(worst_util[0]),
            )
        for condition, index in (
            (AlertCondition.VRAM_ABOVE.value, 2),
            (AlertCondition.TEMPERATURE_ABOVE.value, 3),
            (AlertCondition.POWER_ABOVE.value, 4),
        ):
            candidates = [r for r in gpu_rows if r[index] is not None]
            if candidates:
                worst = max(candidates, key=lambda r: r[index])
                values[condition] = (float(worst[index]), worst[0], names.get(worst[0]))

    inference = (
        await session.execute(
            select(
                func.avg(InferenceMetric.p95_latency_ms),
                func.avg(InferenceMetric.requests_per_second),
                func.avg(InferenceMetric.error_rate),
            ).where(
                InferenceMetric.data_source == data_source,
                InferenceMetric.bucket_start >= since,
            )
        )
    ).one()
    if inference[0] is not None:
        values[AlertCondition.P95_LATENCY_ABOVE.value] = (float(inference[0]), None, "inference")
    if inference[1] is not None:
        values[AlertCondition.THROUGHPUT_BELOW.value] = (float(inference[1]), None, "inference")
    if inference[2] is not None:
        values[AlertCondition.ERROR_RATE_ABOVE.value] = (float(inference[2]), None, "inference")

    try:
        from app.services.cost_service import summarize_cost

        cost = await summarize_cost(
            session, time_range=resolve_range("1h"), data_source=data_source
        )
        values[AlertCondition.COST_ABOVE.value] = (cost.total_cost, None, "cost")
    except Exception as exc:
        logger.debug("cost_alert_value_unavailable", error=str(exc)[:160])

    return values


def _breached(condition: str, value: float, threshold: float) -> bool:
    if condition.endswith("_below"):
        return value < threshold
    return value > threshold


async def evaluate(
    session: AsyncSession, *, data_source: str = DataSource.PRODUCTION.value
) -> list[Alert]:
    """Evaluate all enabled rules; fire new alerts and auto-resolve recovered ones."""
    rules = list(
        (
            await session.execute(
                select(AlertRule).where(
                    AlertRule.data_source == data_source, AlertRule.is_enabled.is_(True)
                )
            )
        )
        .scalars()
        .all()
    )
    if not rules:
        return []

    values = await _current_values(session, data_source=data_source)
    now = datetime.now(timezone.utc)
    fired: list[Alert] = []

    for rule in rules:
        observation = values.get(rule.condition)
        if observation is None:
            continue
        value, entity_id, entity_label = observation

        active = (
            (
                await session.execute(
                    select(Alert).where(
                        Alert.rule_id == rule.id,
                        Alert.state.in_([AlertState.ACTIVE.value, AlertState.ACKNOWLEDGED.value]),
                    )
                )
            )
            .scalars()
            .first()
        )

        if _breached(rule.condition, value, rule.threshold):
            if active is not None:
                active.observed_value = value  # refresh the live reading
                continue
            if (
                rule.last_fired_at
                and (now - _aware(rule.last_fired_at)).total_seconds() < rule.cooldown_seconds
            ):
                continue

            alert = Alert(
                rule_id=rule.id,
                title=rule.name,
                condition=rule.condition,
                severity=rule.severity,
                state=AlertState.ACTIVE.value,
                data_source=data_source,
                entity_type="gpu" if entity_id else "deployment",
                entity_id=entity_id,
                entity_label=entity_label,
                observed_value=value,
                threshold=rule.threshold,
                message=(
                    f"{rule.name}: observed {value:.4g} against threshold {rule.threshold:.4g}."
                ),
                triggered_at=now,
            )
            session.add(alert)
            rule.last_fired_at = now
            fired.append(alert)
            ALERTS_FIRED.labels(condition=rule.condition, severity=rule.severity).inc()
        elif active is not None:
            active.state = AlertState.RESOLVED.value
            active.resolved_at = now
            active.resolve_reason = (
                f"Condition cleared: observed {value:.4g} against threshold {rule.threshold:.4g}."
            )

    await session.commit()
    await refresh_active_gauge(session, data_source=data_source)
    if fired:
        logger.info("alerts_fired", count=len(fired), data_source=data_source)
    return fired


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


async def acknowledge(
    session: AsyncSession, alert_id: str, *, actor: str, note: str | None = None
) -> Alert:
    alert = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if alert is None:
        raise NotFoundError("Alert not found.")
    if alert.state == AlertState.RESOLVED.value:
        raise ConflictError("This alert is already resolved and cannot be acknowledged.")
    if alert.state == AlertState.ACKNOWLEDGED.value:
        raise ConflictError("This alert has already been acknowledged.")

    alert.state = AlertState.ACKNOWLEDGED.value
    alert.acknowledged_at = datetime.now(timezone.utc)
    alert.acknowledged_by = actor
    alert.acknowledge_note = note
    await session.commit()
    await session.refresh(alert)
    await record_audit(
        action="alert.acknowledge",
        resource_type="alert",
        resource_id=alert_id,
        actor_label=actor,
        detail={"note": note},
    )
    await refresh_active_gauge(session, data_source=alert.data_source)
    return alert


async def resolve(
    session: AsyncSession, alert_id: str, *, actor: str, reason: str | None = None
) -> Alert:
    alert = (await session.execute(select(Alert).where(Alert.id == alert_id))).scalar_one_or_none()
    if alert is None:
        raise NotFoundError("Alert not found.")
    if alert.state == AlertState.RESOLVED.value:
        raise ConflictError("This alert is already resolved.")

    alert.state = AlertState.RESOLVED.value
    alert.resolved_at = datetime.now(timezone.utc)
    alert.resolve_reason = reason or f"Manually resolved by {actor}."
    await session.commit()
    await session.refresh(alert)
    await record_audit(
        action="alert.resolve", resource_type="alert", resource_id=alert_id, actor_label=actor
    )
    await refresh_active_gauge(session, data_source=alert.data_source)
    return alert


async def summarize(session: AsyncSession, *, data_source: str) -> AlertSummary:
    rows = list(
        (
            await session.execute(
                select(Alert.state, Alert.severity, func.count(Alert.id))
                .where(Alert.data_source == data_source)
                .group_by(Alert.state, Alert.severity)
            )
        ).all()
    )
    summary = AlertSummary()
    for state, severity, count in rows:
        count = int(count)
        if state == AlertState.ACTIVE.value:
            summary.active += count
            summary.by_severity[severity] = summary.by_severity.get(severity, 0) + count
        elif state == AlertState.ACKNOWLEDGED.value:
            summary.acknowledged += count

    since = datetime.now(timezone.utc) - timedelta(hours=24)
    summary.resolved_24h = int(
        await session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(
                Alert.data_source == data_source,
                Alert.state == AlertState.RESOLVED.value,
                Alert.resolved_at >= since,
            )
        )
        or 0
    )
    return summary


async def refresh_active_gauge(session: AsyncSession, *, data_source: str) -> None:
    rows = list(
        (
            await session.execute(
                select(Alert.severity, func.count(Alert.id))
                .where(Alert.data_source == data_source, Alert.state == AlertState.ACTIVE.value)
                .group_by(Alert.severity)
            )
        ).all()
    )
    counts = {s.value: 0 for s in Severity}
    for severity, count in rows:
        counts[severity] = int(count)
    for severity, count in counts.items():
        ALERTS_ACTIVE.labels(severity=severity).set(count)


async def count_active(session: AsyncSession, *, data_source: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(Alert)
            .where(Alert.data_source == data_source, Alert.state == AlertState.ACTIVE.value)
        )
        or 0
    )
