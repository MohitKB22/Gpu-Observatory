"""NVIDIA AI Performance Observatory -- FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from app.api.v1 import api_router, websocket_router
from app.api.v1.health import VERSION
from app.api.v1.health import router as health_router
from app.core.cache import close_cache, init_cache
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.metrics import BUILD_INFO
from app.core.middleware import register_middleware
from app.db.session import dispose_engine, get_sessionmaker
from app.models.enums import DataSource

logger = get_logger(__name__)

DESCRIPTION = """
Observability and performance-optimisation platform for NVIDIA AI inference
workloads.

**Telemetry integrity.** Every telemetry row carries a `data_source`
discriminator of either `production` or `demo`, and every read path filters on
it. Synthetic Demo Mode data is never mixed with, or presented as, real
production telemetry. When no NVIDIA GPU is present the API reports that
plainly rather than fabricating hardware statistics.

**Diagnostics.** Root-cause findings come from a deterministic rules engine
that runs against stored measurements. A language model, when configured, adds
narration on top of those findings -- it never supplies the numbers.

**Cost.** All cost figures are estimates derived from a configurable pricing
profile. They are not billing data.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown: dependencies, seed data, background workers."""
    configure_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
    logger.info(
        "application_starting",
        version=VERSION,
        environment=settings.ENVIRONMENT,
        demo_mode=settings.DEMO_MODE,
        auth_enabled=settings.AUTH_ENABLED,
    )
    if not settings.AUTH_ENABLED:
        logger.warning(
            "authentication_disabled",
            detail="Every caller is treated as an administrator. Never do this in production.",
        )

    BUILD_INFO.labels(
        version=VERSION,
        environment=settings.ENVIRONMENT,
        demo_mode=str(settings.DEMO_MODE).lower(),
    ).set(1)

    await init_cache()
    maker = get_sessionmaker()

    # Seed the data every screen depends on, tolerating a cold database.
    try:
        async with maker() as session:
            from app.services.alert_service import ensure_default_rules
            from app.services.auth_service import ensure_bootstrap_admin
            from app.services.cost_service import ensure_default_pricing

            await ensure_bootstrap_admin(session)
            await ensure_default_pricing(session)
            await ensure_default_rules(session, data_source=DataSource.PRODUCTION.value)
            if settings.DEMO_MODE:
                await ensure_default_rules(session, data_source=DataSource.DEMO.value)
    except Exception as exc:
        logger.error(
            "startup_seed_failed",
            error=str(exc)[:300],
            hint="Has `alembic upgrade head` been run against this database?",
        )

    from app.realtime.workers import supervisor

    await supervisor.start(maker)

    if settings.DEMO_MODE:
        from app.demo.runner import backfill, demo_runtime, ensure_demo_registry

        try:
            async with maker() as session:
                await ensure_demo_registry(session)
                from sqlalchemy import func, select

                from app.models.telemetry import GpuMetric

                existing = await session.scalar(
                    select(func.count())
                    .select_from(GpuMetric)
                    .where(GpuMetric.data_source == DataSource.DEMO.value)
                )
                if not existing:
                    logger.info("demo_backfill_starting")
                    await backfill(session, minutes=90)
            await demo_runtime.start(maker)
        except Exception as exc:
            logger.error("demo_mode_startup_failed", error=str(exc)[:300])

    logger.info("application_ready", version=VERSION)
    try:
        yield
    finally:
        logger.info("application_stopping")
        if settings.DEMO_MODE:
            from app.demo.runner import demo_runtime

            await demo_runtime.stop()
        await supervisor.stop()
        await close_cache()
        await dispose_engine()
        logger.info("application_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description=DESCRIPTION,
        version=VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        swagger_ui_parameters={"defaultModelsExpandDepth": 0, "displayRequestDuration": True},
        contact={"name": "NVIDIA AI Performance Observatory"},
        license_info={"name": "Apache-2.0"},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "X-Response-Time-Ms", "X-RateLimit-Remaining"],
        max_age=600,
    )
    register_middleware(app)
    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(websocket_router)

    @app.get("/", include_in_schema=False)
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "name": settings.APP_NAME,
                "version": VERSION,
                "environment": settings.ENVIRONMENT,
                "demo_mode": settings.DEMO_MODE,
                "docs": "/docs",
                "health": "/health",
                "readiness": "/ready",
                "metrics": "/metrics",
                "api": settings.API_V1_PREFIX,
            }
        )

    def custom_openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        schema.setdefault("components", {})["securitySchemes"] = {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "JWT",
                "description": (
                    "Supply either a JWT access token from POST /api/v1/auth/login "
                    "or an API key beginning with the configured prefix."
                ),
            }
        }
        schema["security"] = [{"BearerAuth": []}]
        schema["tags"] = [
            {"name": "health", "description": "Liveness, readiness and Prometheus metrics."},
            {"name": "auth", "description": "Sessions, users, API keys and the audit log."},
            {"name": "telemetry", "description": "GPU and host telemetry."},
            {"name": "inference", "description": "Models, deployments and inference performance."},
            {
                "name": "analytics",
                "description": "Anomalies, alerts, diagnostics, cost and the AI agent.",
            },
            {"name": "workloads", "description": "Demo Mode and synthetic workload generation."},
            {"name": "realtime", "description": "WebSocket live telemetry."},
        ]
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT in ("local", "development"),
        log_config=None,
    )
