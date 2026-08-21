"""Model registry, deployments, inference performance and comparison endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select

from app.core.audit import record_audit
from app.core.deps import (
    CurrentPrincipal,
    DataSourceParam,
    DbSession,
    PaginationParam,
    require_scope,
)
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.timerange import resolve_range
from app.models.enums import Scope
from app.models.inference import Deployment, InferenceRequest, MLModel
from app.schemas.common import Page, PageMeta, TimeSeriesResponse
from app.schemas.inference import (
    BatchAnalysis,
    ComparisonResponse,
    DeploymentCreate,
    DeploymentOut,
    InferenceRequestIngest,
    InferenceRequestOut,
    InferenceSummary,
    LatencyBucket,
    ModelCreate,
    ModelOut,
    ModelPerformance,
    ModelUpdate,
)
from app.services import comparison_service, inference_service

router = APIRouter(tags=["inference"])

ReadModels = Depends(require_scope(Scope.MODELS_READ))
WriteModels = Depends(require_scope(Scope.MODELS_WRITE))
ReadTelemetry = Depends(require_scope(Scope.TELEMETRY_READ))
WriteTelemetry = Depends(require_scope(Scope.TELEMETRY_WRITE))

RangeQuery = Annotated[str, Query(description="Preset window, e.g. 5m, 1h, 24h, 7d.")]


# ------------------------------------------------------------------ models ---
@router.get(
    "/models", response_model=Page[ModelOut], summary="List models", dependencies=[ReadModels]
)
async def list_models(
    session: DbSession,
    data_source: DataSourceParam,
    pagination: PaginationParam,
    search: Annotated[str | None, Query(max_length=200)] = None,
    framework: Annotated[str | None, Query(max_length=30)] = None,
    sort: Annotated[str, Query(pattern="^(name|created_at|version)$")] = "name",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
) -> Page[ModelOut]:
    stmt = select(MLModel).where(MLModel.data_source == data_source)
    if search:
        stmt = stmt.where(MLModel.name.ilike(f"%{search}%"))
    if framework:
        stmt = stmt.where(MLModel.framework == framework)

    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    column = {"name": MLModel.name, "created_at": MLModel.created_at, "version": MLModel.version}[
        sort
    ]
    stmt = stmt.order_by(column.desc() if order == "desc" else column.asc())
    rows = list(
        (await session.execute(stmt.limit(pagination.limit).offset(pagination.offset)))
        .scalars()
        .all()
    )
    return Page[ModelOut](
        items=[ModelOut.model_validate(r) for r in rows],
        meta=PageMeta(
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(rows) < total,
        ),
    )


@router.post(
    "/models",
    response_model=ModelOut,
    status_code=status.HTTP_201_CREATED,
    summary="Register a model",
    dependencies=[WriteModels],
)
async def create_model(
    payload: ModelCreate,
    session: DbSession,
    data_source: DataSourceParam,
    principal: CurrentPrincipal,
) -> ModelOut:
    duplicate = await session.scalar(
        select(MLModel).where(
            MLModel.name == payload.name,
            MLModel.version == payload.version,
            MLModel.data_source == data_source,
        )
    )
    if duplicate is not None:
        raise ConflictError(
            "A model with that name and version already exists in this data source.",
            details={"name": payload.name, "version": payload.version},
        )

    model = MLModel(**payload.model_dump(), data_source=data_source)
    session.add(model)
    await session.commit()
    await session.refresh(model)
    await record_audit(
        action="model.create",
        resource_type="model",
        resource_id=model.id,
        actor_id=principal.id,
        actor_label=principal.label,
        detail={"name": model.name, "version": model.version},
    )
    return ModelOut.model_validate(model)


@router.get(
    "/models/{model_id}", response_model=ModelOut, summary="Get a model", dependencies=[ReadModels]
)
async def get_model(model_id: str, session: DbSession, data_source: DataSourceParam) -> ModelOut:
    model = await session.scalar(
        select(MLModel).where(MLModel.id == model_id, MLModel.data_source == data_source)
    )
    if model is None:
        raise NotFoundError("Model not found.", details={"model_id": model_id})
    return ModelOut.model_validate(model)


@router.patch(
    "/models/{model_id}",
    response_model=ModelOut,
    summary="Update a model",
    dependencies=[WriteModels],
)
async def update_model(
    model_id: str,
    payload: ModelUpdate,
    session: DbSession,
    data_source: DataSourceParam,
    principal: CurrentPrincipal,
) -> ModelOut:
    model = await session.scalar(
        select(MLModel).where(MLModel.id == model_id, MLModel.data_source == data_source)
    )
    if model is None:
        raise NotFoundError("Model not found.", details={"model_id": model_id})
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(model, field, value)
    await session.commit()
    await session.refresh(model)
    await record_audit(
        action="model.update",
        resource_type="model",
        resource_id=model_id,
        actor_id=principal.id,
        actor_label=principal.label,
    )
    return ModelOut.model_validate(model)


@router.get(
    "/models/{model_id}/performance",
    response_model=ModelPerformance,
    summary="Model performance rollup",
    dependencies=[ReadModels],
)
async def model_performance(
    model_id: str, session: DbSession, data_source: DataSourceParam, range: RangeQuery = "1h"
) -> ModelPerformance:
    model = await session.scalar(
        select(MLModel).where(MLModel.id == model_id, MLModel.data_source == data_source)
    )
    if model is None:
        raise NotFoundError("Model not found.", details={"model_id": model_id})
    return await comparison_service.model_performance(
        session, model=model, time_range=resolve_range(range), data_source=data_source
    )


# ------------------------------------------------------------- deployments ---
@router.get(
    "/deployments",
    response_model=list[DeploymentOut],
    summary="List deployments",
    dependencies=[ReadModels],
)
async def list_deployments(
    session: DbSession,
    data_source: DataSourceParam,
    model_id: Annotated[str | None, Query()] = None,
) -> list[DeploymentOut]:
    stmt = select(Deployment).where(Deployment.data_source == data_source)
    if model_id:
        stmt = stmt.where(Deployment.model_id == model_id)
    rows = list((await session.execute(stmt.order_by(Deployment.name))).scalars().all())
    return [DeploymentOut.model_validate(r) for r in rows]


@router.post(
    "/deployments",
    response_model=DeploymentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a deployment",
    dependencies=[WriteModels],
)
async def create_deployment(
    payload: DeploymentCreate,
    session: DbSession,
    data_source: DataSourceParam,
    principal: CurrentPrincipal,
) -> DeploymentOut:
    model = await session.scalar(
        select(MLModel).where(MLModel.id == payload.model_id, MLModel.data_source == data_source)
    )
    if model is None:
        raise ValidationError(
            "The referenced model does not exist in this data source.",
            details={"model_id": payload.model_id},
        )
    deployment = Deployment(**payload.model_dump(), data_source=data_source)
    session.add(deployment)
    await session.commit()
    await session.refresh(deployment)
    await record_audit(
        action="deployment.create",
        resource_type="deployment",
        resource_id=deployment.id,
        actor_id=principal.id,
        actor_label=principal.label,
    )
    return DeploymentOut.model_validate(deployment)


# --------------------------------------------------------------- inference ---
@router.get(
    "/inference/metrics",
    response_model=InferenceSummary,
    summary="Inference performance summary",
    dependencies=[ReadTelemetry],
)
async def inference_metrics(
    session: DbSession,
    data_source: DataSourceParam,
    range: RangeQuery = "1h",
    start: datetime | None = None,
    end: datetime | None = None,
    deployment_id: Annotated[str | None, Query()] = None,
    model_id: Annotated[str | None, Query()] = None,
) -> InferenceSummary:
    summary = await inference_service.summarize(
        session,
        time_range=resolve_range(range, start, end),
        data_source=data_source,
        deployment_id=deployment_id,
        model_id=model_id,
    )
    from app.services.telemetry_service import telemetry_freshness

    summary.freshness = await telemetry_freshness(session, data_source=data_source)
    if summary.avg_batch_size is not None and summary.max_batch_size:
        summary.batch_efficiency = round(summary.avg_batch_size / summary.max_batch_size, 4)
    return summary


@router.get(
    "/inference/latency",
    response_model=list[LatencyBucket],
    summary="Latency distribution",
    dependencies=[ReadTelemetry],
)
async def inference_latency(
    session: DbSession,
    data_source: DataSourceParam,
    range: RangeQuery = "1h",
    deployment_id: Annotated[str | None, Query()] = None,
    bins: Annotated[int, Query(ge=4, le=100)] = 24,
) -> list[LatencyBucket]:
    return await inference_service.latency_distribution(
        session,
        time_range=resolve_range(range),
        data_source=data_source,
        deployment_id=deployment_id,
        bins=bins,
    )


@router.get(
    "/inference/series",
    response_model=TimeSeriesResponse,
    summary="Inference time-series",
    dependencies=[ReadTelemetry],
)
async def inference_series(
    session: DbSession,
    data_source: DataSourceParam,
    range: RangeQuery = "1h",
    start: datetime | None = None,
    end: datetime | None = None,
    metrics: str = "requests_per_second,p95_latency_ms,tokens_per_second",
    deployment_id: Annotated[str | None, Query()] = None,
) -> TimeSeriesResponse:
    time_range = resolve_range(range, start, end)
    allowed = {
        "requests_per_second",
        "avg_latency_ms",
        "p50_latency_ms",
        "p90_latency_ms",
        "p95_latency_ms",
        "p99_latency_ms",
        "tokens_per_second",
        "error_rate",
        "avg_batch_size",
        "avg_concurrency",
        "avg_queue_latency_ms",
    }
    fields = [f.strip() for f in metrics.split(",") if f.strip() in allowed] or [
        "requests_per_second"
    ]
    series = await inference_service.inference_series(
        session,
        time_range=time_range,
        data_source=data_source,
        fields=fields,
        deployment_id=deployment_id,
    )
    from app.services.telemetry_service import telemetry_freshness

    return TimeSeriesResponse(
        range_label=time_range.label,
        start=time_range.start,
        end=time_range.end,
        bucket_seconds=time_range.bucket_seconds,
        data_source=data_source,
        series=series,
        freshness=await telemetry_freshness(session, data_source=data_source),
    )


@router.get(
    "/inference/requests",
    response_model=Page[InferenceRequestOut],
    summary="Request performance table",
    dependencies=[ReadTelemetry],
)
async def inference_requests(
    session: DbSession,
    data_source: DataSourceParam,
    pagination: PaginationParam,
    range: RangeQuery = "1h",
    errors_only: bool = False,
    deployment_id: Annotated[str | None, Query()] = None,
    sort: Annotated[str, Query(pattern="^(started_at|total_latency_ms)$")] = "started_at",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
) -> Page[InferenceRequestOut]:
    time_range = resolve_range(range)
    stmt = select(InferenceRequest).where(
        InferenceRequest.data_source == data_source,
        InferenceRequest.started_at >= time_range.start,
        InferenceRequest.started_at <= time_range.end,
    )
    if errors_only:
        stmt = stmt.where(InferenceRequest.is_error.is_(True))
    if deployment_id:
        stmt = stmt.where(InferenceRequest.deployment_id == deployment_id)

    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    column = {
        "started_at": InferenceRequest.started_at,
        "total_latency_ms": InferenceRequest.total_latency_ms,
    }[sort]
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
    return Page[InferenceRequestOut](
        items=[InferenceRequestOut.model_validate(r) for r in rows],
        meta=PageMeta(
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(rows) < total,
        ),
    )


@router.post(
    "/inference/requests",
    summary="Record observed inference requests",
    dependencies=[WriteTelemetry],
)
async def record_inference_requests(
    payload: list[InferenceRequestIngest], session: DbSession
) -> dict:
    """Ingestion endpoint used by the inference gateway."""
    if not payload:
        raise ValidationError("At least one request record is required.")
    if len(payload) > 1000:
        raise ValidationError("A maximum of 1000 records may be submitted per call.")

    by_source: dict[str, list[dict]] = {}
    for item in payload:
        by_source.setdefault(item.data_source, []).append(item.model_dump(exclude={"data_source"}))
    written = 0
    for source, records in by_source.items():
        written += await inference_service.record_requests(session, records, data_source=source)
    return {"accepted": True, "records": written}


@router.get(
    "/batches",
    response_model=BatchAnalysis,
    summary="Batching analytics",
    dependencies=[ReadTelemetry],
)
async def batches(
    session: DbSession,
    data_source: DataSourceParam,
    range: RangeQuery = "1h",
    deployment_id: Annotated[str | None, Query()] = None,
) -> BatchAnalysis:
    return await inference_service.analyse_batching(
        session,
        time_range=resolve_range(range),
        data_source=data_source,
        deployment_id=deployment_id,
    )


@router.get(
    "/comparisons/models",
    response_model=ComparisonResponse,
    summary="Compare models side by side",
    dependencies=[ReadModels],
)
async def compare_models(
    session: DbSession,
    data_source: DataSourceParam,
    model_ids: Annotated[str, Query(description="Comma-separated model ids (2-6).")],
    range: RangeQuery = "1h",
) -> ComparisonResponse:
    ids = [m.strip() for m in model_ids.split(",") if m.strip()]
    return await comparison_service.compare(
        session, model_ids=ids, time_range=resolve_range(range), data_source=data_source
    )
