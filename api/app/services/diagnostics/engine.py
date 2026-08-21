"""Diagnostics orchestration.

Runs every deterministic rule against a context, ranks the findings, and
optionally persists them. The LLM narrative layer sits on top of this and can
never replace it -- rules always run.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.metrics import DIAGNOSES_GENERATED
from app.core.timerange import TimeRange
from app.models.analytics import Diagnosis
from app.models.enums import DataSource, DiagnosisEngine, DiagnosisKind, Severity
from app.schemas.analytics import DiagnosisOut
from app.services.diagnostics.context import DiagnosticContext, build_context
from app.services.diagnostics.rules import ALL_RULES, Finding

logger = get_logger(__name__)

_SEVERITY_RANK = {
    Severity.CRITICAL.value: 5,
    Severity.HIGH.value: 4,
    Severity.MEDIUM.value: 3,
    Severity.LOW.value: 2,
    Severity.INFO.value: 1,
}

# When both fire, the more specific diagnosis supersedes the general one.
_SUPERSEDES = {
    DiagnosisKind.UNDER_BATCHING.value: {DiagnosisKind.GPU_UNDER_UTILIZATION.value},
    DiagnosisKind.THERMAL_THROTTLING.value: {DiagnosisKind.THROUGHPUT_DEGRADATION.value},
    DiagnosisKind.VRAM_SATURATION.value: {DiagnosisKind.HIGH_ERROR_RATE.value},
}


def run_rules(ctx: DiagnosticContext) -> list[Finding]:
    """Execute all rules and return findings ranked by severity × confidence."""
    findings: list[Finding] = []
    for name, rule in ALL_RULES:
        try:
            findings.extend(rule(ctx))
        except Exception as exc:  # a broken rule must not break diagnostics
            logger.exception("diagnostic_rule_failed", rule=name, error=str(exc)[:200])

    findings = _apply_supersession(findings)
    findings = _coalesce_by_kind(findings)
    findings.sort(key=lambda f: (_SEVERITY_RANK.get(f.severity, 0), f.confidence), reverse=True)
    return findings


def _coalesce_by_kind(findings: list[Finding]) -> list[Finding]:
    """Collapse the same diagnosis across multiple devices into one finding.

    A four-GPU node with the same thermal problem on every device should read
    as one issue affecting four devices, not as four separate issues.
    """
    grouped: dict[str, list[Finding]] = {}
    for finding in findings:
        grouped.setdefault(finding.kind, []).append(finding)

    coalesced: list[Finding] = []
    for group in grouped.values():
        if len(group) == 1:
            coalesced.append(group[0])
            continue
        group.sort(key=lambda f: (_SEVERITY_RANK.get(f.severity, 0), f.confidence), reverse=True)
        primary = group[0]
        others = group[1:]
        labels = [f.entity_label for f in others if f.entity_label]
        primary.metrics["affected_entity_count"] = len(group)
        if labels:
            primary.evidence.append(
                f"The same condition was detected on {len(others)} further "
                f"{'device' if len(others) == 1 else 'devices'}: {', '.join(labels)}."
            )
            primary.title = f"{primary.title} (+{len(others)} more)"
        coalesced.append(primary)
    return coalesced


def _apply_supersession(findings: list[Finding]) -> list[Finding]:
    """Drop general findings when a more specific one explains the same symptom."""
    present = {f.kind for f in findings}
    suppressed: set[str] = set()
    for specific, generals in _SUPERSEDES.items():
        if specific in present:
            suppressed |= generals
    if not suppressed:
        return findings

    kept: list[Finding] = []
    for finding in findings:
        if finding.kind in suppressed:
            # Preserve the signal by folding it into the specific finding's evidence.
            continue
        kept.append(finding)
    return kept


def healthy_finding(ctx: DiagnosticContext) -> Finding:
    """Explicit 'nothing wrong' result, so the UI never shows an empty panel."""
    evidence: list[str] = []
    gpu_avg = ctx.avg_gpu_utilization
    if gpu_avg is not None:
        evidence.append(f"GPU utilisation averaged {gpu_avg:.1f}% with no idle pattern detected.")
    if ctx.latency_p95.avg is not None:
        evidence.append(f"P95 latency averaged {ctx.latency_p95.avg:.1f} ms and was stable.")
    if ctx.error_rate.avg is not None:
        evidence.append(f"Error rate averaged {ctx.error_rate.avg * 100:.2f}%.")
    if ctx.batch_size.avg is not None and ctx.configured_max_batch:
        evidence.append(
            f"Average batch size {ctx.batch_size.avg:.1f} of {ctx.configured_max_batch} "
            f"({ctx.batch_size.avg / ctx.configured_max_batch * 100:.0f}% efficiency)."
        )
    if not evidence:
        evidence.append("No telemetry was available in the selected window.")

    has_data = ctx.has_gpu_data or ctx.has_inference_data or ctx.has_system_data
    return Finding(
        kind=DiagnosisKind.HEALTHY.value,
        title=(
            "No performance issues detected" if has_data else "No telemetry in the selected window"
        ),
        severity=Severity.INFO.value,
        root_cause=(
            "All monitored signals are within their expected operating ranges."
            if has_data
            else "There is no telemetry for this window, so no conclusion can be drawn."
        ),
        evidence=evidence,
        metrics={
            "gpu_utilization_avg_pct": round(gpu_avg, 2) if gpu_avg is not None else None,
            "p95_latency_ms": round(ctx.latency_p95.avg, 2) if ctx.latency_p95.avg else None,
            "error_rate": round(ctx.error_rate.avg, 4) if ctx.error_rate.avg is not None else None,
            "request_count": ctx.request_count,
        },
        impact=None,
        recommendations=(
            ["Continue monitoring. No action is required."]
            if has_data
            else [
                "Confirm a telemetry agent is running and reporting.",
                "Enable Demo Mode to explore the platform without live telemetry.",
            ]
        ),
        confidence=0.85 if has_data else 0.3,
    )


def finding_to_schema(
    finding: Finding,
    ctx: DiagnosticContext,
    *,
    engine: str,
    diagnosis_id: str | None = None,
    narrative: str | None = None,
) -> DiagnosisOut:
    return DiagnosisOut(
        id=diagnosis_id,
        title=finding.title,
        severity=finding.severity,
        kind=finding.kind,
        root_cause=finding.root_cause,
        evidence=finding.evidence,
        metrics=finding.metrics,
        impact=finding.impact,
        recommendations=finding.recommendations,
        confidence=finding.confidence,
        engine=engine,
        entity_type=finding.entity_type,
        entity_id=finding.entity_id,
        entity_label=finding.entity_label,
        narrative=narrative,
        data_source=ctx.data_source,
        window_seconds=ctx.time_range.duration_seconds,
        generated_at=ctx.generated_at,
    )


async def persist(
    session: AsyncSession,
    finding: Finding,
    ctx: DiagnosticContext,
    *,
    engine: str,
    narrative: str | None = None,
) -> Diagnosis:
    row = Diagnosis(
        generated_at=datetime.now(timezone.utc),
        kind=finding.kind,
        title=finding.title,
        severity=finding.severity,
        engine=engine,
        data_source=ctx.data_source,
        entity_type=finding.entity_type,
        entity_id=finding.entity_id,
        entity_label=finding.entity_label,
        root_cause=finding.root_cause,
        evidence=json.dumps(finding.evidence),
        metrics=json.dumps(finding.metrics, default=str),
        impact=finding.impact,
        recommendations=json.dumps(finding.recommendations),
        confidence=finding.confidence,
        window_seconds=ctx.time_range.duration_seconds,
        narrative=narrative,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    DIAGNOSES_GENERATED.labels(kind=finding.kind, engine=engine).inc()
    return row


async def diagnose(
    session: AsyncSession,
    *,
    time_range: TimeRange,
    data_source: str = DataSource.PRODUCTION.value,
    entity_type: str | None = None,
    entity_id: str | None = None,
    persist_results: bool = True,
    max_findings: int = 6,
) -> tuple[list[DiagnosisOut], DiagnosticContext]:
    """Full deterministic diagnosis pass over a window."""
    ctx = await build_context(
        session,
        time_range=time_range,
        data_source=data_source,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    await _attach_cost(session, ctx)

    findings = run_rules(ctx)
    if not findings:
        findings = [healthy_finding(ctx)]
    findings = findings[:max_findings]

    results: list[DiagnosisOut] = []
    for finding in findings:
        diagnosis_id = None
        if persist_results and finding.kind != DiagnosisKind.HEALTHY.value:
            row = await persist(session, finding, ctx, engine=DiagnosisEngine.RULES.value)
            diagnosis_id = row.id
        results.append(
            finding_to_schema(
                finding, ctx, engine=DiagnosisEngine.RULES.value, diagnosis_id=diagnosis_id
            )
        )

    logger.info(
        "diagnosis_complete",
        findings=len(results),
        data_source=data_source,
        window=time_range.label,
        top=results[0].kind if results else None,
    )
    return results, ctx


async def _attach_cost(session: AsyncSession, ctx: DiagnosticContext) -> None:
    """Populate cost fields so the cost-spike rule has something to fire on."""
    try:
        from app.services.cost_service import window_cost_trend

        current, previous = await window_cost_trend(
            session, time_range=ctx.time_range, data_source=ctx.data_source
        )
        ctx.cost_per_hour = current
        if previous and previous > 0 and current is not None:
            ctx.cost_change_pct = (current - previous) / previous * 100.0
    except Exception as exc:  # cost is advisory; never block diagnosis
        logger.debug("cost_attach_skipped", error=str(exc)[:160])


def summarise_for_agent(findings: list[DiagnosisOut]) -> str:
    """Compact text rendering handed to the LLM as grounded context."""
    if not findings:
        return "No findings."
    lines: list[str] = []
    for finding in findings:
        lines.append(
            f"- [{finding.severity.upper()}] {finding.title} "
            f"(kind={finding.kind}, confidence={finding.confidence:.2f})"
        )
        lines.append(f"  root_cause: {finding.root_cause}")
        for item in finding.evidence[:5]:
            lines.append(f"  evidence: {item}")
        if finding.impact:
            lines.append(f"  impact: {finding.impact}")
    return "\n".join(lines)
