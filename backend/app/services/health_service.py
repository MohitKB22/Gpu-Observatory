"""Connection checks for registered models, on demand and on a schedule."""

import asyncio
import contextlib
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import HealthCheck, RegisteredModel
from app.models.enums import HealthStatus, ModelStatus
from app.monitoring.prometheus import MODEL_UP
from app.providers.base import ProviderError
from app.providers.registry import ProviderRegistry
from app.security import SecretBox
from app.services.model_service import build_endpoint_config

logger = logging.getLogger(__name__)


async def run_health_check(
    session: AsyncSession, model: RegisteredModel, providers: ProviderRegistry, secret_box: SecretBox
) -> HealthCheck:
    started = time.perf_counter()
    error: ProviderError | None = None
    try:
        endpoint = build_endpoint_config(model, secret_box)
        await providers.get(model.provider).check_health(endpoint)
    except ProviderError as exc:
        error = exc
    latency_ms = (time.perf_counter() - started) * 1000
    checked_at = datetime.now(UTC)

    check = HealthCheck(
        model_id=model.id,
        checked_at=checked_at,
        status=HealthStatus.UNHEALTHY.value if error else HealthStatus.HEALTHY.value,
        latency_ms=latency_ms,
        error_kind=error.kind.value if error else None,
        error_message=error.message if error else None,
    )
    model.status = ModelStatus.UNHEALTHY.value if error else ModelStatus.HEALTHY.value
    model.last_checked_at = checked_at
    model.last_check_latency_ms = latency_ms
    model.last_error = error.message if error else None
    session.add(check)
    await session.commit()

    MODEL_UP.labels(model.name, model.provider).set(0 if error else 1)
    logger.info(
        "connection check finished",
        extra={
            "model": model.name,
            "provider": model.provider,
            "healthy": error is None,
            "latency_ms": round(latency_ms, 1),
        },
    )
    return check


async def list_health_checks(session: AsyncSession, model_id: uuid.UUID, limit: int) -> list[HealthCheck]:
    result = await session.scalars(
        select(HealthCheck).where(HealthCheck.model_id == model_id).order_by(HealthCheck.checked_at.desc()).limit(limit)
    )
    return list(result)


class HealthCheckScheduler:
    """Periodically checks every enabled model and prunes old check history."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        providers: ProviderRegistry,
        secret_box: SecretBox,
        interval_seconds: int,
        retention_days: int,
    ):
        self._session_factory = session_factory
        self._providers = providers
        self._secret_box = secret_box
        self._interval = interval_seconds
        self._retention = timedelta(days=retention_days)
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="health-check-scheduler")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def run_once(self) -> None:
        async with self._session_factory() as session:
            model_ids = list(await session.scalars(select(RegisteredModel.id).where(RegisteredModel.is_enabled)))
        # Each check gets its own session so one slow endpoint does not hold up the others.
        await asyncio.gather(*(self._check_one(model_id) for model_id in model_ids))
        await self._prune_history()

    async def _check_one(self, model_id: uuid.UUID) -> None:
        try:
            async with self._session_factory() as session:
                model = await session.get(RegisteredModel, model_id)
                if model is not None:
                    await run_health_check(session, model, self._providers, self._secret_box)
        except Exception:
            logger.exception("scheduled connection check failed", extra={"model_id": str(model_id)})

    async def _prune_history(self) -> None:
        cutoff = datetime.now(UTC) - self._retention
        async with self._session_factory() as session:
            await session.execute(delete(HealthCheck).where(HealthCheck.checked_at < cutoff))
            await session.commit()

    async def _run(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                logger.exception("health check cycle failed")
            await asyncio.sleep(self._interval)
