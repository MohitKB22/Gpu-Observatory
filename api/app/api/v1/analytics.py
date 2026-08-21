"""Anomaly, alert, diagnostics, cost and agent endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import func, select

from app.agents.copilot import get_copilot
from app.core.deps import (
    CurrentPrincipal,
    DataSourceParam,
    DbSession,
    PaginationParam,
    require_scope,
)
from app.core.errors import NotFoundError
from app.core.timerange import resolve_range
from app.models.analytics import Alert, AlertRule, Anomaly, Diagnosis, PricingProfile
from app.models.enums import DiagnosisEngine, Scope
from app.schemas.agent import AgentCapabilities, AgentChatRequest, AgentChatResponse
from app.schemas.analytics import (
    AlertAcknowledge,
    AlertOut,
    AlertRuleCreate,
    AlertRuleOut,
    AlertSummary,
    AnomalyOut,
    CostSummary,
    DiagnosisOut,
    DiagnosisReport,
    DiagnosisRequest,
    PricingCreate,
    PricingOut,
)
from app.schemas.common import Page, PageMeta
from app.services import alert_service, anomaly_service, cost_service
from app.services.diagnostics import diagnose

router = APIRouter(tags=["analytics"])

ReadAlerts = Depends(require_scope(Scope.ALERTS_READ))
WriteAlerts = Depends(require_scope(Scope.ALERTS_WRITE))
ReadDiagnostics = Depends(require_scope(Scope.DIAGNOSTICS_READ))
RunDiagnostics = Depends(require_scope(Scope.DIAGNOSTICS_RUN))
ReadCost = Depends(require_scope(Scope.COST_READ))
AgentChat = Depends(require_scope(Scope.AGENT_CHAT))

RangeQuery = Annotated[str, Query(description="Preset window, e.g. 5m, 1h, 24h, 7d.")]


# --------------------------------------------------------------- anomalies ---
@router.get(
    "/anomalies",
    response_model=Page[AnomalyOut],
    summary="List anomalies",
    dependencies=[ReadDiagnostics],
)
async def list_anomalies(
    session: DbSession,
    data_source: DataSourceParam,
    pagination: PaginationParam,
    range: RangeQuery = "24h",
    severity: Annotated[str | None, Query(pattern="^(info|low|medium|high|critical)$")] = None,
    metric_kind: Annotated[str | None, Query(max_length=40)] = None,
) -> Page[AnomalyOut]:
    time_range = resolve_range(range)
    stmt = select(Anomaly).where(
        Anomaly.data_source == data_source,
        Anomaly.detected_at >= time_range.start,
        Anomaly.detected_at <= time_range.end,
    )
    if severity:
        stmt = stmt.where(Anomaly.severity == severity)
    if metric_kind:
        stmt = stmt.where(Anomaly.metric_kind == metric_kind)

    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(
        (
            await session.execute(
                stmt.order_by(Anomaly.detected_at.desc())
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page[AnomalyOut](
        items=[AnomalyOut.model_validate(r) for r in rows],
        meta=PageMeta(
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(rows) < total,
        ),
    )


@router.post(
    "/anomalies/scan",
    response_model=list[AnomalyOut],
    summary="Run an anomaly scan",
    dependencies=[RunDiagnostics],
)
async def scan_anomalies(
    session: DbSession,
    data_source: DataSourceParam,
    window_minutes: Annotated[int, Query(ge=5, le=1440)] = 60,
) -> list[AnomalyOut]:
    rows = await anomaly_service.scan(
        session, data_source=data_source, window_minutes=window_minutes
    )
    return [AnomalyOut.model_validate(r) for r in rows]


# ------------------------------------------------------------------ alerts ---
@router.get(
    "/alerts", response_model=Page[AlertOut], summary="List alerts", dependencies=[ReadAlerts]
)
async def list_alerts(
    session: DbSession,
    data_source: DataSourceParam,
    pagination: PaginationParam,
    state: Annotated[str | None, Query(pattern="^(active|acknowledged|resolved)$")] = None,
    severity: Annotated[str | None, Query(pattern="^(info|low|medium|high|critical)$")] = None,
    sort: Annotated[str, Query(pattern="^(triggered_at|severity)$")] = "triggered_at",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[AlertOut]:
    stmt = select(Alert).where(Alert.data_source == data_source)
    if state:
        stmt = stmt.where(Alert.state == state)
    if severity:
        stmt = stmt.where(Alert.severity == severity)

    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    column = {"triggered_at": Alert.triggered_at, "severity": Alert.severity}[sort]
    rows = list(
        (
            await session.execute(
                stmt.order_by(column.desc() if order == "desc" else column.asc())
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page[AlertOut](
        items=[AlertOut.model_validate(r) for r in rows],
        meta=PageMeta(
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(rows) < total,
        ),
    )


@router.get(
    "/alerts/summary",
    response_model=AlertSummary,
    summary="Alert counts",
    dependencies=[ReadAlerts],
)
async def alert_summary(session: DbSession, data_source: DataSourceParam) -> AlertSummary:
    return await alert_service.summarize(session, data_source=data_source)


@router.post(
    "/alerts/{alert_id}/acknowledge",
    response_model=AlertOut,
    summary="Acknowledge an alert",
    dependencies=[WriteAlerts],
)
async def acknowledge_alert(
    alert_id: str, payload: AlertAcknowledge, session: DbSession, principal: CurrentPrincipal
) -> AlertOut:
    alert = await alert_service.acknowledge(
        session, alert_id, actor=principal.label or principal.id or "unknown", note=payload.note
    )
    return AlertOut.model_validate(alert)


@router.post(
    "/alerts/{alert_id}/resolve",
    response_model=AlertOut,
    summary="Resolve an alert",
    dependencies=[WriteAlerts],
)
async def resolve_alert(
    alert_id: str,
    session: DbSession,
    principal: CurrentPrincipal,
    reason: Annotated[str | None, Query(max_length=300)] = None,
) -> AlertOut:
    alert = await alert_service.resolve(
        session, alert_id, actor=principal.label or principal.id or "unknown", reason=reason
    )
    return AlertOut.model_validate(alert)


@router.post(
    "/alerts/evaluate",
    response_model=list[AlertOut],
    summary="Force an alert evaluation",
    dependencies=[WriteAlerts],
)
async def evaluate_alerts(session: DbSession, data_source: DataSourceParam) -> list[AlertOut]:
    fired = await alert_service.evaluate(session, data_source=data_source)
    return [AlertOut.model_validate(a) for a in fired]


@router.get(
    "/alert-rules",
    response_model=list[AlertRuleOut],
    summary="List alert rules",
    dependencies=[ReadAlerts],
)
async def list_alert_rules(session: DbSession, data_source: DataSourceParam) -> list[AlertRuleOut]:
    rows = list(
        (
            await session.execute(
                select(AlertRule)
                .where(AlertRule.data_source == data_source)
                .order_by(AlertRule.name)
            )
        )
        .scalars()
        .all()
    )
    return [AlertRuleOut.model_validate(r) for r in rows]


@router.post(
    "/alert-rules",
    response_model=AlertRuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an alert rule",
    dependencies=[WriteAlerts],
)
async def create_alert_rule(
    payload: AlertRuleCreate, session: DbSession, data_source: DataSourceParam
) -> AlertRuleOut:
    rule = AlertRule(**payload.model_dump(), data_source=data_source)
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return AlertRuleOut.model_validate(rule)


@router.delete(
    "/alert-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete an alert rule",
    dependencies=[WriteAlerts],
)
async def delete_alert_rule(rule_id: str, session: DbSession) -> Response:
    rule = await session.scalar(select(AlertRule).where(AlertRule.id == rule_id))
    if rule is None:
        raise NotFoundError("Alert rule not found.")
    await session.delete(rule)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------- diagnostics ---
@router.post(
    "/diagnostics",
    response_model=DiagnosisReport,
    summary="Run a root-cause diagnosis",
    dependencies=[RunDiagnostics],
)
async def run_diagnostics(
    payload: DiagnosisRequest, session: DbSession, data_source: DataSourceParam
) -> DiagnosisReport:
    """Run the deterministic engine, optionally enriched with an LLM narrative."""
    time_range = resolve_range(payload.range)
    findings, ctx = await diagnose(
        session,
        time_range=time_range,
        data_source=data_source,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        persist_results=payload.persist,
    )

    engine = DiagnosisEngine.RULES.value
    copilot = get_copilot()
    if payload.use_llm and copilot.provider.available and findings:
        try:
            from app.services.diagnostics.engine import summarise_for_agent

            narrative = await _narrate(copilot, summarise_for_agent(findings), data_source)
            if narrative:
                findings[0].narrative = narrative
                engine = DiagnosisEngine.HYBRID.value
        except Exception:
            pass  # narrative is optional enrichment

    return DiagnosisReport(
        findings=findings,
        analysed_window=time_range.label,
        data_source=data_source,
        engine=engine,
        generated_at=ctx.generated_at,
    )


async def _narrate(copilot, grounding: str, data_source: str) -> str | None:
    from app.agents.llm import LLMMessage

    response = await copilot.provider.complete(
        [
            LLMMessage(
                "system",
                "You are an NVIDIA AI infrastructure analyst. Summarise the supplied "
                "findings in two or three sentences for an on-call engineer. Use only "
                "the numbers provided; never introduce new figures.",
            ),
            LLMMessage("user", f"Data source: {data_source}\n\nFindings:\n{grounding}"),
        ],
        tools=None,
        max_tokens=400,
    )
    return response.content.strip() if response.ok and response.content else None


@router.get(
    "/diagnostics/history",
    response_model=Page[DiagnosisOut],
    summary="Diagnosis history",
    dependencies=[ReadDiagnostics],
)
async def diagnostics_history(
    session: DbSession,
    data_source: DataSourceParam,
    pagination: PaginationParam,
    kind: Annotated[str | None, Query(max_length=50)] = None,
    severity: Annotated[str | None, Query(pattern="^(info|low|medium|high|critical)$")] = None,
) -> Page[DiagnosisOut]:
    stmt = select(Diagnosis).where(Diagnosis.data_source == data_source)
    if kind:
        stmt = stmt.where(Diagnosis.kind == kind)
    if severity:
        stmt = stmt.where(Diagnosis.severity == severity)

    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(
        (
            await session.execute(
                stmt.order_by(Diagnosis.generated_at.desc())
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
        )
        .scalars()
        .all()
    )
    items = [
        DiagnosisOut(
            id=r.id,
            title=r.title,
            severity=r.severity,
            kind=r.kind,
            root_cause=r.root_cause,
            evidence=_load_list(r.evidence),
            metrics=_load_dict(r.metrics),
            impact=r.impact,
            recommendations=_load_list(r.recommendations),
            confidence=r.confidence,
            engine=r.engine,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            entity_label=r.entity_label,
            narrative=r.narrative,
            data_source=r.data_source,
            window_seconds=r.window_seconds,
            generated_at=r.generated_at,
        )
        for r in rows
    ]
    return Page[DiagnosisOut](
        items=items,
        meta=PageMeta(
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(rows) < total,
        ),
    )


def _load_list(raw: str | None) -> list[str]:
    try:
        value = json.loads(raw or "[]")
        return [str(v) for v in value] if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


def _load_dict(raw: str | None) -> dict:
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


# -------------------------------------------------------------------- cost ---
@router.get("/cost", response_model=CostSummary, summary="Cost summary", dependencies=[ReadCost])
async def cost(
    session: DbSession,
    data_source: DataSourceParam,
    range: RangeQuery = "24h",
    start: datetime | None = None,
    end: datetime | None = None,
    pricing_id: Annotated[str | None, Query()] = None,
) -> CostSummary:
    profile = None
    if pricing_id:
        profile = await session.scalar(
            select(PricingProfile).where(PricingProfile.id == pricing_id)
        )
        if profile is None:
            raise NotFoundError("Pricing profile not found.", details={"pricing_id": pricing_id})
    return await cost_service.summarize_cost(
        session,
        time_range=resolve_range(range, start, end),
        data_source=data_source,
        pricing=profile,
    )


@router.get(
    "/cost/pricing",
    response_model=list[PricingOut],
    summary="List pricing profiles",
    dependencies=[ReadCost],
)
async def list_pricing(session: DbSession) -> list[PricingOut]:
    rows = list(
        (await session.execute(select(PricingProfile).order_by(PricingProfile.name)))
        .scalars()
        .all()
    )
    return [PricingOut.model_validate(r) for r in rows]


@router.post(
    "/cost/pricing",
    response_model=PricingOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pricing profile",
    dependencies=[WriteAlerts],
)
async def create_pricing(payload: PricingCreate, session: DbSession) -> PricingOut:
    if payload.is_default:
        for existing in (
            (
                await session.execute(
                    select(PricingProfile).where(PricingProfile.is_default.is_(True))
                )
            )
            .scalars()
            .all()
        ):
            existing.is_default = False

    profile = PricingProfile(
        **payload.model_dump(), is_estimate=True, effective_from=datetime.now(timezone.utc)
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return PricingOut.model_validate(profile)


# ------------------------------------------------------------------- agent ---
@router.post(
    "/agent/chat",
    response_model=AgentChatResponse,
    summary="Ask the NVIDIA Performance Copilot",
    dependencies=[AgentChat],
)
async def agent_chat(
    payload: AgentChatRequest, session: DbSession, data_source: DataSourceParam
) -> AgentChatResponse:
    return await get_copilot().chat(session, payload, data_source=data_source)


@router.get(
    "/agent/capabilities",
    response_model=AgentCapabilities,
    summary="Agent tools and provider status",
    dependencies=[ReadDiagnostics],
)
async def agent_capabilities() -> AgentCapabilities:
    return get_copilot().capabilities()
