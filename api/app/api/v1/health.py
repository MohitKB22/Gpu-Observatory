"""Liveness, readiness and Prometheus exposition endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Response, status

from app.core.cache import check_cache
from app.core.config import settings
from app.core.metrics import DEPENDENCY_UP, render_metrics
from app.db.session import check_database
from app.schemas.common import HealthComponent, HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])
_STARTED_AT = time.time()
VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    """Process liveness. Never touches dependencies, so it stays fast."""
    return HealthResponse(
        status="ok",
        version=VERSION,
        environment=settings.ENVIRONMENT,
        demo_mode=settings.DEMO_MODE,
        uptime_seconds=round(time.time() - _STARTED_AT, 2),
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/live", response_model=HealthResponse, summary="Kubernetes liveness alias")
async def live() -> HealthResponse:
    return await health()


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness probe")
async def ready(response: Response) -> ReadinessResponse:
    """Readiness. Verifies the database and cache before declaring ready."""
    components: list[HealthComponent] = []

    started = time.perf_counter()
    db_ok, db_detail = await check_database()
    components.append(
        HealthComponent(
            name="database",
            healthy=db_ok,
            detail=db_detail,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    )
    DEPENDENCY_UP.labels(dependency="database").set(1 if db_ok else 0)

    started = time.perf_counter()
    cache_ok, cache_backend = await check_cache()
    components.append(
        HealthComponent(
            name="cache",
            healthy=cache_ok,
            detail=f"backend={cache_backend}",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    )
    DEPENDENCY_UP.labels(dependency="cache").set(1 if cache_ok else 0)

    # The database is the only hard dependency; the cache degrades to memory.
    is_ready = db_ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        ready=is_ready,
        components=components,
        timestamp=datetime.now(timezone.utc),
    )


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    response_class=Response,
    responses={200: {"content": {"text/plain": {}}}},
)
async def metrics() -> Response:
    """Prometheus text exposition for the platform's own telemetry."""
    return Response(
        content=render_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
