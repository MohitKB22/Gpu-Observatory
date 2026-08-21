"""Agent tools.

Every tool is READ-ONLY and operates through the same service layer the API
uses, so tool results are exactly the numbers the dashboard shows. The agent
has no tool that can execute shell commands, mutate configuration, read
secrets, or write to the database -- the capability simply does not exist in
this registry, rather than being blocked by a prompt instruction.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import AGENT_TOOL_CALLS
from app.core.timerange import resolve_range
from app.models.analytics import Alert, Anomaly, Diagnosis
from app.models.enums import AlertState
from app.services import (
    alert_service,
    comparison_service,
    cost_service,
    inference_service,
    telemetry_service,
)

logger = get_logger(__name__)

MAX_RANGE = "24h"


@dataclass
class ToolContext:
    """Everything a tool is permitted to see."""

    session: AsyncSession
    data_source: str
    default_range: str = "1h"
    entity_type: str | None = None
    entity_id: str | None = None


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str | None = None
    summary: str | None = None


ToolFn = Callable[[ToolContext, dict[str, Any]], Awaitable[ToolResult]]


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolFn
    read_only: bool = True


def _range_arg(args: dict[str, Any], context: ToolContext) -> str:
    """Clamp any caller-supplied range to a supported preset."""
    requested = str(args.get("range") or context.default_range)
    allowed = {"5m", "15m", "1h", "6h", "24h", "7d"}
    return requested if requested in allowed else context.default_range


# ------------------------------------------------------------------- tools ---
async def _get_current_gpu_metrics(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    gpus = await telemetry_service.list_gpus(ctx.session, data_source=ctx.data_source)
    if not gpus:
        return ToolResult(
            True,
            {"gpus": [], "gpu_count": 0},
            summary="No GPUs are registered in this data source.",
        )
    rows: list[dict[str, Any]] = []
    for gpu in gpus:
        latest = await telemetry_service.latest_gpu_metric(
            ctx.session, gpu.id, data_source=ctx.data_source
        )
        rows.append(
            {
                "gpu_id": gpu.id,
                "index": gpu.index,
                "name": gpu.name,
                "utilization_pct": _r(latest.utilization_pct) if latest else None,
                "vram_utilization_pct": _r(latest.memory_utilization_pct) if latest else None,
                "vram_used_mb": _r(latest.memory_used_mb) if latest else None,
                "vram_total_mb": _r(latest.memory_total_mb) if latest else None,
                "temperature_c": _r(latest.temperature_c) if latest else None,
                "power_w": _r(latest.power_w) if latest else None,
                "power_limit_w": _r(latest.power_limit_w) if latest else None,
                "sm_clock_mhz": latest.sm_clock_mhz if latest else None,
                "throttle_reasons": (latest.throttle_reasons or "") if latest else None,
                "recorded_at": latest.recorded_at.isoformat() if latest else None,
            }
        )
    summary = "; ".join(
        f"GPU {r['index']}: util {r['utilization_pct']}%, VRAM {r['vram_utilization_pct']}%, "
        f"{r['temperature_c']}°C"
        for r in rows[:4]
    )
    return ToolResult(True, {"gpus": rows, "gpu_count": len(rows)}, summary=summary)


async def _get_gpu_history(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    time_range = resolve_range(_range_arg(args, ctx))
    field = str(args.get("metric") or "utilization_pct")
    allowed = {
        "utilization_pct",
        "memory_utilization_pct",
        "memory_used_mb",
        "temperature_c",
        "power_w",
        "sm_clock_mhz",
    }
    if field not in allowed:
        return ToolResult(False, error=f"Unsupported metric '{field}'. Allowed: {sorted(allowed)}")

    series = await telemetry_service.gpu_series(
        ctx.session,
        time_range=time_range,
        data_source=ctx.data_source,
        gpu_ids=[args["gpu_id"]] if args.get("gpu_id") else None,
        fields=[field],
    )
    payload = []
    for item in series:
        values = [p.value for p in item.points if p.value is not None]
        if not values:
            continue
        payload.append(
            {
                "entity": item.entity_label,
                "metric": field,
                "points": len(values),
                "first": _r(values[0]),
                "last": _r(values[-1]),
                "min": _r(min(values)),
                "max": _r(max(values)),
                "avg": _r(sum(values) / len(values)),
            }
        )
    return ToolResult(
        True,
        {"range": time_range.label, "metric": field, "series": payload},
        summary=f"{len(payload)} GPU series for {field} over {time_range.label}.",
    )


async def _get_cpu_metrics(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    latest = await telemetry_service.latest_system_metric(ctx.session, data_source=ctx.data_source)
    if latest is None:
        return ToolResult(True, {"available": False}, summary="No host telemetry available.")
    return ToolResult(
        True,
        {
            "available": True,
            "host": latest.host,
            "cpu_utilization_pct": _r(latest.cpu_utilization_pct),
            "core_count": latest.core_count,
            "load_avg_1m": _r(latest.load_avg_1m),
            "ram_utilization_pct": _r(latest.ram_utilization_pct),
            "ram_used_mb": _r(latest.ram_used_mb),
            "swap_used_mb": _r(latest.swap_used_mb),
            "disk_utilization_pct": _r(latest.disk_utilization_pct),
            "process_count": latest.process_count,
            "recorded_at": latest.recorded_at.isoformat(),
        },
        summary=(
            f"CPU {_r(latest.cpu_utilization_pct)}%, RAM {_r(latest.ram_utilization_pct)}% "
            f"on {latest.host}."
        ),
    )


async def _get_inference_metrics(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    time_range = resolve_range(_range_arg(args, ctx))
    summary = await inference_service.summarize(
        ctx.session,
        time_range=time_range,
        data_source=ctx.data_source,
        deployment_id=args.get("deployment_id"),
    )
    return ToolResult(
        True,
        {
            "range": time_range.label,
            "request_count": summary.request_count,
            "error_count": summary.error_count,
            "error_rate": _r(summary.error_rate, 5),
            "requests_per_second": _r(summary.requests_per_second, 3),
            "avg_latency_ms": _r(summary.latency.avg),
            "p95_latency_ms": _r(summary.latency.p95),
            "tokens_per_second": _r(summary.tokens_per_second),
            "avg_batch_size": _r(summary.avg_batch_size),
            "total_input_tokens": summary.total_input_tokens,
            "total_output_tokens": summary.total_output_tokens,
        },
        summary=(
            f"{summary.request_count} requests over {time_range.label}, "
            f"P95 {_r(summary.latency.p95)} ms, {_r(summary.requests_per_second, 2)} req/s."
        ),
    )


async def _get_latency_percentiles(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    time_range = resolve_range(_range_arg(args, ctx))
    summary = await inference_service.summarize(
        ctx.session,
        time_range=time_range,
        data_source=ctx.data_source,
        deployment_id=args.get("deployment_id"),
    )
    latency = summary.latency
    return ToolResult(
        True,
        {
            "range": time_range.label,
            "p50_ms": _r(latency.p50),
            "p90_ms": _r(latency.p90),
            "p95_ms": _r(latency.p95),
            "p99_ms": _r(latency.p99),
            "avg_ms": _r(latency.avg),
            "min_ms": _r(latency.min),
            "max_ms": _r(latency.max),
            "queue_ms": _r(summary.breakdown.queue_ms),
            "execution_ms": _r(summary.breakdown.execution_ms),
            "sample_size": summary.request_count,
        },
        summary=f"P50 {_r(latency.p50)} ms, P95 {_r(latency.p95)} ms, P99 {_r(latency.p99)} ms.",
    )


async def _get_model_metrics(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    time_range = resolve_range(_range_arg(args, ctx))
    models = await inference_service.list_models(ctx.session, data_source=ctx.data_source)
    if not models:
        return ToolResult(True, {"models": []}, summary="No models are registered.")

    name_filter = str(args.get("model_name") or "").lower().strip()
    if name_filter:
        models = [m for m in models if name_filter in m.name.lower()] or models

    rows = []
    for model in models[:8]:
        performance = await comparison_service.model_performance(
            ctx.session, model=model, time_range=time_range, data_source=ctx.data_source
        )
        rows.append(performance.model_dump())
    return ToolResult(
        True,
        {"range": time_range.label, "models": rows},
        summary=f"Performance for {len(rows)} model(s) over {time_range.label}.",
    )


async def _compare_models(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    time_range = resolve_range(_range_arg(args, ctx))
    model_ids = args.get("model_ids") or []
    if not isinstance(model_ids, list) or len(model_ids) < 2:
        # Fall back to comparing the models that actually have data.
        models = await inference_service.list_models(ctx.session, data_source=ctx.data_source)
        model_ids = [m.id for m in models[:3]]
    if len(model_ids) < 2:
        return ToolResult(False, error="At least two registered models are required to compare.")

    try:
        comparison = await comparison_service.compare(
            ctx.session,
            model_ids=[str(m) for m in model_ids][:6],
            time_range=time_range,
            data_source=ctx.data_source,
        )
    except Exception as exc:
        return ToolResult(False, error=str(exc)[:300])

    return ToolResult(
        True,
        {
            "range": time_range.label,
            "models": [m.model_dump() for m in comparison.models],
            "recommendation": comparison.recommendation,
            "recommended_model_id": comparison.recommended_model_id,
            "confidence": comparison.confidence,
            "caveats": comparison.caveats,
        },
        summary=comparison.recommendation or "No clear recommendation from the measured data.",
    )


async def _get_batch_metrics(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    time_range = resolve_range(_range_arg(args, ctx))
    analysis = await inference_service.analyse_batching(
        ctx.session,
        time_range=time_range,
        data_source=ctx.data_source,
        deployment_id=args.get("deployment_id"),
    )
    return ToolResult(
        True,
        {
            "range": time_range.label,
            "avg_batch_size": analysis.avg_batch_size,
            "max_batch_size": analysis.max_batch_size,
            "configured_max_batch_size": analysis.configured_max_batch_size,
            "batch_efficiency": analysis.batch_efficiency,
            "avg_queue_depth": analysis.avg_queue_depth,
            "avg_batch_formation_ms": analysis.avg_batch_formation_ms,
            "avg_gpu_utilization": analysis.avg_gpu_utilization,
            "under_batching_detected": analysis.under_batching_detected,
            "over_batching_detected": analysis.over_batching_detected,
            "headroom_pct": analysis.headroom_pct,
        },
        summary=(
            f"Average batch {_r(analysis.avg_batch_size)} of "
            f"{analysis.configured_max_batch_size}; under-batching="
            f"{analysis.under_batching_detected}."
        ),
    )


async def _get_cost_metrics(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    time_range = resolve_range(_range_arg(args, ctx))
    cost = await cost_service.summarize_cost(
        ctx.session, time_range=time_range, data_source=ctx.data_source
    )
    return ToolResult(
        True,
        {
            "range": time_range.label,
            "currency": cost.currency,
            "pricing_profile": cost.pricing_profile,
            "cost_per_gpu_hour": cost.cost_per_gpu_hour,
            "gpu_hours": cost.gpu_hours,
            "total_cost": cost.total_cost,
            "cost_per_request": cost.cost_per_request,
            "cost_per_1m_tokens": cost.cost_per_1m_tokens,
            "projected_monthly_cost": cost.projected_monthly_cost,
            "is_estimate": True,
            "note": cost_service.ESTIMATE_NOTE,
        },
        summary=(
            f"Estimated {cost.currency} {cost.total_cost} over {time_range.label} "
            f"({cost.gpu_hours} GPU-hours)."
        ),
    )


async def _get_recent_alerts(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    limit = min(int(args.get("limit") or 10), 50)
    stmt = select(Alert).where(Alert.data_source == ctx.data_source)
    if args.get("state") in {s.value for s in AlertState}:
        stmt = stmt.where(Alert.state == args["state"])
    rows = list(
        (await ctx.session.execute(stmt.order_by(Alert.triggered_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    summary_counts = await alert_service.summarize(ctx.session, data_source=ctx.data_source)
    return ToolResult(
        True,
        {
            "alerts": [
                {
                    "id": a.id,
                    "title": a.title,
                    "severity": a.severity,
                    "state": a.state,
                    "condition": a.condition,
                    "observed_value": _r(a.observed_value),
                    "threshold": _r(a.threshold),
                    "triggered_at": a.triggered_at.isoformat(),
                    "entity_label": a.entity_label,
                }
                for a in rows
            ],
            "active_count": summary_counts.active,
            "acknowledged_count": summary_counts.acknowledged,
        },
        summary=f"{summary_counts.active} active alert(s); returned {len(rows)} recent.",
    )


async def _query_historical_incidents(ctx: ToolContext, args: dict[str, Any]) -> ToolResult:
    """Past diagnoses and anomalies -- the agent's memory of prior incidents."""
    limit = min(int(args.get("limit") or 10), 50)
    hours = min(int(args.get("hours") or 24), 720)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    diagnosis_stmt = select(Diagnosis).where(
        Diagnosis.data_source == ctx.data_source, Diagnosis.generated_at >= since
    )
    if args.get("kind"):
        diagnosis_stmt = diagnosis_stmt.where(Diagnosis.kind == str(args["kind"]))
    diagnoses = list(
        (
            await ctx.session.execute(
                diagnosis_stmt.order_by(Diagnosis.generated_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )
    anomalies = list(
        (
            await ctx.session.execute(
                select(Anomaly)
                .where(Anomaly.data_source == ctx.data_source, Anomaly.detected_at >= since)
                .order_by(Anomaly.detected_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return ToolResult(
        True,
        {
            "window_hours": hours,
            "diagnoses": [
                {
                    "id": d.id,
                    "kind": d.kind,
                    "title": d.title,
                    "severity": d.severity,
                    "confidence": d.confidence,
                    "generated_at": d.generated_at.isoformat(),
                    "root_cause": d.root_cause,
                }
                for d in diagnoses
            ],
            "anomalies": [
                {
                    "metric_kind": a.metric_kind,
                    "severity": a.severity,
                    "score": a.score,
                    "observed_value": a.observed_value,
                    "expected_value": a.expected_value,
                    "detected_at": a.detected_at.isoformat(),
                    "description": a.description,
                }
                for a in anomalies
            ],
        },
        summary=(
            f"{len(diagnoses)} prior diagnosis/es and {len(anomalies)} anomaly/ies "
            f"in the last {hours}h."
        ),
    )


def _r(value: Any, digits: int = 2) -> Any:
    return round(float(value), digits) if isinstance(value, int | float) else value


_RANGE_PARAM = {
    "type": "string",
    "enum": ["5m", "15m", "1h", "6h", "24h", "7d"],
    "description": "Time window to analyse.",
}

TOOLS: list[ToolSpec] = [
    ToolSpec(
        "get_current_gpu_metrics",
        "Current utilisation, VRAM, temperature, power and clocks for every registered GPU.",
        {"type": "object", "properties": {}},
        _get_current_gpu_metrics,
    ),
    ToolSpec(
        "get_gpu_history",
        "Historical statistics for one GPU metric over a time window.",
        {
            "type": "object",
            "properties": {
                "range": _RANGE_PARAM,
                "metric": {
                    "type": "string",
                    "enum": [
                        "utilization_pct",
                        "memory_utilization_pct",
                        "memory_used_mb",
                        "temperature_c",
                        "power_w",
                        "sm_clock_mhz",
                    ],
                },
                "gpu_id": {"type": "string", "description": "Restrict to one GPU."},
            },
        },
        _get_gpu_history,
    ),
    ToolSpec(
        "get_cpu_metrics",
        "Latest host CPU, RAM, swap and disk utilisation.",
        {"type": "object", "properties": {}},
        _get_cpu_metrics,
    ),
    ToolSpec(
        "get_inference_metrics",
        "Aggregate inference statistics: volume, error rate, throughput, tokens and batch size.",
        {
            "type": "object",
            "properties": {"range": _RANGE_PARAM, "deployment_id": {"type": "string"}},
        },
        _get_inference_metrics,
    ),
    ToolSpec(
        "get_latency_percentiles",
        "Latency percentiles (P50/P90/P95/P99) and the queue/execution breakdown.",
        {
            "type": "object",
            "properties": {"range": _RANGE_PARAM, "deployment_id": {"type": "string"}},
        },
        _get_latency_percentiles,
    ),
    ToolSpec(
        "get_model_metrics",
        "Per-model performance rollup including latency, throughput, cost and error rate.",
        {
            "type": "object",
            "properties": {"range": _RANGE_PARAM, "model_name": {"type": "string"}},
        },
        _get_model_metrics,
    ),
    ToolSpec(
        "compare_models",
        "Compare two or more models and return a computed recommendation.",
        {
            "type": "object",
            "properties": {
                "range": _RANGE_PARAM,
                "model_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
        _compare_models,
    ),
    ToolSpec(
        "get_batch_metrics",
        "Batching analytics: batch size versus configured maximum, efficiency, queue depth.",
        {
            "type": "object",
            "properties": {"range": _RANGE_PARAM, "deployment_id": {"type": "string"}},
        },
        _get_batch_metrics,
    ),
    ToolSpec(
        "get_cost_metrics",
        "Estimated cost: GPU-hours, cost per request and per million tokens.",
        {"type": "object", "properties": {"range": _RANGE_PARAM}},
        _get_cost_metrics,
    ),
    ToolSpec(
        "get_recent_alerts",
        "Recent alerts and current active/acknowledged counts.",
        {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "state": {"type": "string", "enum": ["active", "acknowledged", "resolved"]},
            },
        },
        _get_recent_alerts,
    ),
    ToolSpec(
        "query_historical_incidents",
        "Previously recorded diagnoses and anomalies, for comparison against the present.",
        {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "minimum": 1, "maximum": 720},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
                "kind": {"type": "string"},
            },
        },
        _query_historical_incidents,
    ),
]

TOOL_REGISTRY: dict[str, ToolSpec] = {t.name: t for t in TOOLS}


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters} for t in TOOLS
    ]


async def invoke(name: str, ctx: ToolContext, args: dict[str, Any]) -> tuple[ToolResult, float]:
    """Dispatch a tool call. Unknown names are refused, not guessed at."""
    spec = TOOL_REGISTRY.get(name)
    started = time.perf_counter()
    if spec is None:
        AGENT_TOOL_CALLS.labels(tool=name or "unknown", outcome="unknown_tool").inc()
        return (
            ToolResult(False, error=f"Unknown tool '{name}'. This tool is not available."),
            0.0,
        )
    if not spec.read_only:  # defence in depth: the registry contains no such tool
        AGENT_TOOL_CALLS.labels(tool=name, outcome="forbidden").inc()
        return ToolResult(False, error="Write tools are not permitted."), 0.0

    try:
        result = await spec.handler(ctx, args or {})
    except Exception as exc:
        logger.exception("agent_tool_failed", tool=name, error=str(exc)[:200])
        AGENT_TOOL_CALLS.labels(tool=name, outcome="error").inc()
        return (
            ToolResult(False, error=f"Tool '{name}' failed: {str(exc)[:200]}"),
            (time.perf_counter() - started) * 1000,
        )

    AGENT_TOOL_CALLS.labels(tool=name, outcome="ok" if result.ok else "error").inc()
    return result, (time.perf_counter() - started) * 1000
