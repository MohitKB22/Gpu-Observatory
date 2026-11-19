"""Application factory.

Run with:  uvicorn --factory app.main:create_app
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.error_handlers import register_error_handlers
from app.api.middleware import RequestLoggingMiddleware
from app.api.routes import analytics, inference, infrastructure, logs, metrics, models, system
from app.config import Settings, get_settings
from app.db.connectivity import DatabaseUnavailableError, check_database_connection
from app.db.session import create_engine, create_session_factory
from app.logging_config import configure_logging
from app.monitoring.gpu_metrics import GpuMonitor
from app.monitoring.sampler import SystemSampler
from app.providers.registry import ProviderRegistry
from app.security import SecretBox
from app.services.demo_seed import bootstrap_demo_data
from app.services.health_service import HealthCheckScheduler

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, http_transport: httpx.AsyncBaseTransport | None = None) -> FastAPI:
    """`http_transport` lets tests replace outbound HTTP to inference endpoints with a mock."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        try:
            await check_database_connection(engine, settings.database_url)
        except DatabaseUnavailableError as exc:
            # Logged first so the cause is the first thing on screen; uvicorn prints the traceback after it.
            logger.error(str(exc))
            await engine.dispose()
            raise
        session_factory = create_session_factory(engine)
        # Redirects are not followed so a misconfigured endpoint cannot silently bounce
        # requests (and their Authorization header) to another host.
        http_client = httpx.AsyncClient(
            transport=http_transport,
            follow_redirects=False,
            headers={"User-Agent": f"ai-inference-observatory/{__version__}"},
        )
        providers = ProviderRegistry(http_client, simulate_demo_latency=settings.demo_simulate_latency)
        secret_box = SecretBox(settings.secret_key)
        sampler = SystemSampler(
            GpuMonitor(settings.nvidia_smi_path), settings.system_sample_interval_seconds, settings.system_history_size
        )
        scheduler = HealthCheckScheduler(
            session_factory,
            providers,
            secret_box,
            settings.health_check_interval_seconds,
            settings.health_check_retention_days,
        )

        app.state.settings = settings
        app.state.session_factory = session_factory
        app.state.http_client = http_client
        app.state.providers = providers
        app.state.secret_box = secret_box
        app.state.sampler = sampler

        if settings.demo_mode:
            await bootstrap_demo_data(session_factory, settings.demo_seed_history)
        sampler.start()
        if settings.health_check_interval_seconds > 0:
            scheduler.start()
        logger.info("backend started", extra={"environment": settings.app_env, "demo_mode": settings.demo_mode})

        try:
            yield
        finally:
            await scheduler.stop()
            await sampler.stop()
            await http_client.aclose()
            await engine.dispose()

    app = FastAPI(
        title="AI Inference Observatory API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )
    register_error_handlers(app)
    for router in (
        system.router,
        analytics.router,
        models.router,
        inference.router,
        infrastructure.router,
        logs.router,
        metrics.router,
    ):
        app.include_router(router)
    return app
