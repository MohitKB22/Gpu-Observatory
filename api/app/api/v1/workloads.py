"""Demo Mode control and synthetic workload generation."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.core.audit import record_audit
from app.core.config import settings
from app.core.deps import CurrentPrincipal, DbSession, PaginationParam, require_scope
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.demo.runner import available_scenarios, backfill, demo_runtime, reset_demo_data
from app.demo.scenarios import SCENARIOS
from app.models.analytics import Workload
from app.models.enums import DataSource, Scope, WorkloadProfile, WorkloadStatus
from app.schemas.analytics import DemoControl, DemoStateOut, WorkloadCreate, WorkloadOut
from app.schemas.common import MessageResponse, Page, PageMeta
from app.services.workload_service import run_workload

logger = get_logger(__name__)

router = APIRouter(tags=["workloads"])

#: Strong references to detached workload tasks, discarded on completion.
_BACKGROUND_TASKS: set[asyncio.Task] = set()

WriteTelemetry = Depends(require_scope(Scope.TELEMETRY_WRITE))
ReadTelemetry = Depends(require_scope(Scope.TELEMETRY_READ))


# --------------------------------------------------------------- demo mode ---
@router.get(
    "/demo", response_model=DemoStateOut, summary="Demo Mode state", dependencies=[ReadTelemetry]
)
async def demo_state() -> DemoStateOut:
    profile = demo_runtime.generator.profile
    return DemoStateOut(
        enabled=settings.DEMO_MODE,
        scenario=demo_runtime.generator.scenario_key,
        available_scenarios=available_scenarios(),
        gpu_count=len(demo_runtime.generator.gpus),
        interval_seconds=settings.DEMO_INTERVAL_SECONDS,
        running=demo_runtime.running,
        samples_generated=demo_runtime.samples_generated,
        started_at=demo_runtime.started_at,
        description=profile.description,
    )


@router.get("/demo/scenarios", summary="Available demo scenarios", dependencies=[ReadTelemetry])
async def demo_scenarios() -> list[dict]:
    return [
        {
            "key": p.key,
            "title": p.title,
            "description": p.description,
            "expected_diagnosis": p.expected_diagnosis,
        }
        for p in SCENARIOS.values()
    ]


@router.post(
    "/demo/scenario",
    response_model=DemoStateOut,
    summary="Switch demo scenario",
    dependencies=[WriteTelemetry],
)
async def set_demo_scenario(payload: DemoControl, principal: CurrentPrincipal) -> DemoStateOut:
    if not settings.DEMO_MODE:
        raise ConflictError(
            "Demo Mode is disabled. Set DEMO_MODE=true to enable synthetic telemetry."
        )
    try:
        await demo_runtime.set_scenario(payload.scenario)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await record_audit(
        action="demo.scenario_change",
        resource_type="demo",
        resource_id=payload.scenario,
        actor_id=principal.id,
        actor_label=principal.label,
    )
    return await demo_state()


@router.post(
    "/demo/backfill", summary="Seed historical demo telemetry", dependencies=[WriteTelemetry]
)
async def demo_backfill(
    session: DbSession,
    principal: CurrentPrincipal,
    minutes: Annotated[int, Query(ge=5, le=1440)] = 90,
    scenario: Annotated[str | None, Query()] = None,
    reset: bool = False,
) -> dict:
    if not settings.DEMO_MODE:
        raise ConflictError("Demo Mode is disabled.")
    if scenario and scenario not in SCENARIOS:
        raise ValidationError(
            f"Unknown scenario '{scenario}'.", details={"available": available_scenarios()}
        )
    if reset:
        await reset_demo_data(session)
    result = await backfill(session, minutes=minutes, scenario=scenario)
    await record_audit(
        action="demo.backfill",
        resource_type="demo",
        actor_id=principal.id,
        actor_label=principal.label,
        detail={"minutes": minutes, "scenario": scenario, "reset": reset},
    )
    return {"ok": True, **result}


@router.delete(
    "/demo/data",
    response_model=MessageResponse,
    summary="Clear all demo data",
    dependencies=[WriteTelemetry],
)
async def clear_demo_data(session: DbSession, principal: CurrentPrincipal) -> MessageResponse:
    """Removes only demo-namespace rows. Production telemetry is never touched."""
    await reset_demo_data(session)
    await record_audit(
        action="demo.reset",
        resource_type="demo",
        actor_id=principal.id,
        actor_label=principal.label,
    )
    return MessageResponse(message="Demo data cleared. Production telemetry is unaffected.")


# --------------------------------------------------------------- workloads ---
@router.get(
    "/workloads",
    response_model=Page[WorkloadOut],
    summary="List workloads",
    dependencies=[ReadTelemetry],
)
async def list_workloads(
    session: DbSession,
    pagination: PaginationParam,
    status_filter: Annotated[
        str | None, Query(alias="status", pattern="^(pending|running|completed|failed|cancelled)$")
    ] = None,
) -> Page[WorkloadOut]:
    stmt = select(Workload)
    if status_filter:
        stmt = stmt.where(Workload.status == status_filter)
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(
        (
            await session.execute(
                stmt.order_by(Workload.created_at.desc())
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page[WorkloadOut](
        items=[WorkloadOut.model_validate(r) for r in rows],
        meta=PageMeta(
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(rows) < total,
        ),
    )


@router.get(
    "/workloads/profiles", summary="Available workload profiles", dependencies=[ReadTelemetry]
)
async def workload_profiles() -> list[dict]:
    descriptions = {
        WorkloadProfile.LOW_CONCURRENCY.value: (
            "A small number of concurrent clients; batches stay small."
        ),
        WorkloadProfile.HIGH_CONCURRENCY.value: (
            "Many concurrent clients; batches fill and queueing appears."
        ),
        WorkloadProfile.SMALL_BATCH.value: ("Forces small batches to reproduce under-batching."),
        WorkloadProfile.LARGE_BATCH.value: "Drives batches to the configured ceiling.",
        WorkloadProfile.LATENCY_SPIKE.value: (
            "Injects a burst of expensive requests to inflate the tail."
        ),
        WorkloadProfile.MEMORY_PRESSURE.value: ("Long-context requests that grow the KV cache."),
    }
    return [{"key": k, "description": v} for k, v in descriptions.items()]


@router.post(
    "/workloads",
    response_model=WorkloadOut,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a synthetic workload",
    dependencies=[WriteTelemetry],
)
async def create_workload(
    payload: WorkloadCreate, session: DbSession, principal: CurrentPrincipal
) -> WorkloadOut:
    """Generates load through the local inference adapter and records the
    resulting telemetry into the demo namespace."""
    workload = Workload(
        name=payload.name,
        profile=payload.profile,
        status=WorkloadStatus.PENDING.value,
        data_source=DataSource.DEMO.value,
        deployment_id=payload.deployment_id,
        target_rps=payload.target_rps,
        concurrency=payload.concurrency,
        batch_size=payload.batch_size,
        duration_seconds=payload.duration_seconds,
        scenario=payload.scenario,
        parameters=json.dumps(payload.model_dump(), default=str),
    )
    session.add(workload)
    await session.commit()
    await session.refresh(workload)

    # Run detached so the request returns immediately with 202. A strong
    # reference is retained until completion; without one the event loop may
    # garbage-collect the task mid-flight.
    task = asyncio.create_task(
        run_workload(get_sessionmaker(), workload.id), name=f"workload-{workload.id[:8]}"
    )
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    await record_audit(
        action="workload.start",
        resource_type="workload",
        resource_id=workload.id,
        actor_id=principal.id,
        actor_label=principal.label,
        detail={"profile": payload.profile},
    )
    return WorkloadOut.model_validate(workload)


@router.get(
    "/workloads/{workload_id}",
    response_model=WorkloadOut,
    summary="Workload detail",
    dependencies=[ReadTelemetry],
)
async def get_workload(workload_id: str, session: DbSession) -> WorkloadOut:
    workload = await session.scalar(select(Workload).where(Workload.id == workload_id))
    if workload is None:
        raise NotFoundError("Workload not found.", details={"workload_id": workload_id})
    return WorkloadOut.model_validate(workload)


@router.post(
    "/workloads/{workload_id}/cancel",
    response_model=WorkloadOut,
    summary="Cancel a workload",
    dependencies=[WriteTelemetry],
)
async def cancel_workload(workload_id: str, session: DbSession) -> WorkloadOut:
    workload = await session.scalar(select(Workload).where(Workload.id == workload_id))
    if workload is None:
        raise NotFoundError("Workload not found.", details={"workload_id": workload_id})
    if workload.status in (WorkloadStatus.COMPLETED.value, WorkloadStatus.FAILED.value):
        raise ConflictError("This workload has already finished.")
    workload.status = WorkloadStatus.CANCELLED.value
    workload.finished_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(workload)
    return WorkloadOut.model_validate(workload)
