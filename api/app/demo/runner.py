"""Demo Mode runtime.

Owns the background loop that writes synthetic telemetry, and the backfill
routine that seeds history so charts and diagnostics have something to show
immediately after startup.

Every write here is tagged ``data_source='demo'``.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.core.timerange import floor_to_bucket
from app.demo.generator import DemoTelemetryGenerator
from app.demo.scenarios import SCENARIOS
from app.models.enums import (
    DataSource,
    DemoScenario,
    DeploymentStatus,
    ModelFramework,
    Quantization,
)
from app.models.inference import Deployment, MLModel
from app.services import inference_service, telemetry_service

logger = get_logger(__name__)

DEMO_SOURCE = DataSource.DEMO.value
BUCKET_SECONDS = 60

DEMO_MODELS = [
    # (name, version, params_b, quantization, context, max_batch, framework)
    (
        "llama-3.1-8b-instruct",
        "1.0.0",
        8.0,
        Quantization.FP16.value,
        131072,
        32,
        ModelFramework.VLLM.value,
    ),
    (
        "mistral-7b-instruct",
        "0.3.0",
        7.3,
        Quantization.AWQ.value,
        32768,
        48,
        ModelFramework.VLLM.value,
    ),
    (
        "qwen2.5-14b-instruct",
        "1.0.0",
        14.8,
        Quantization.FP8.value,
        32768,
        24,
        ModelFramework.TENSORRT_LLM.value,
    ),
]


class DemoRuntime:
    """Holds demo state for the process."""

    def __init__(self) -> None:
        self.generator = DemoTelemetryGenerator(
            scenario=settings.DEMO_SCENARIO, gpu_count=settings.DEMO_GPU_COUNT
        )
        self.running = False
        self.samples_generated = 0
        self.started_at: datetime | None = None
        self._task: asyncio.Task | None = None
        self._maker: async_sessionmaker[AsyncSession] | None = None

    # ------------------------------------------------------------ lifecycle --
    async def start(self, maker: async_sessionmaker[AsyncSession]) -> None:
        if self.running:
            return
        self._maker = maker
        self.running = True
        self.started_at = datetime.now(timezone.utc)
        self._task = asyncio.create_task(self._loop(), name="demo-telemetry")
        logger.info(
            "demo_mode_started",
            scenario=self.generator.scenario_key,
            gpus=len(self.generator.gpus),
            interval=settings.DEMO_INTERVAL_SECONDS,
        )

    async def stop(self) -> None:
        self.running = False
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        logger.info("demo_mode_stopped")

    async def set_scenario(self, scenario: str) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown demo scenario: {scenario}")
        self.generator.set_scenario(scenario)
        logger.info("demo_scenario_changed", scenario=scenario)

    # ----------------------------------------------------------------- loop --
    async def _loop(self) -> None:
        assert self._maker is not None
        interval = max(1.0, settings.DEMO_INTERVAL_SECONDS)
        while self.running:
            try:
                async with self._maker() as session:
                    await self.tick(session)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("demo_tick_failed", error=str(exc)[:200])
            await asyncio.sleep(interval)

    async def tick(self, session: AsyncSession, at: datetime | None = None) -> None:
        """Produce and persist one interval of demo telemetry."""
        moment = at or datetime.now(timezone.utc)
        self.generator.advance()

        await telemetry_service.record_gpu_samples(
            session,
            self.generator.gpu_samples(moment),
            host="demo-node-01",
            data_source=DEMO_SOURCE,
        )
        await telemetry_service.record_system_sample(
            session, self.generator.system_sample(moment), data_source=DEMO_SOURCE
        )

        deployment = await _default_demo_deployment(session)
        requests = self.generator.inference_requests(
            moment, seconds=max(1.0, settings.DEMO_INTERVAL_SECONDS)
        )
        for request in requests:
            request["deployment_id"] = deployment.id if deployment else None
            request["model_id"] = deployment.model_id if deployment else None
        await inference_service.record_requests(session, requests, data_source=DEMO_SOURCE)

        bucket = floor_to_bucket(moment, BUCKET_SECONDS)
        await inference_service.aggregate_bucket(
            session,
            bucket_start=bucket,
            bucket_seconds=BUCKET_SECONDS,
            data_source=DEMO_SOURCE,
            deployment_id=deployment.id if deployment else None,
        )
        await inference_service.record_batch_metric(
            session,
            bucket_start=bucket,
            bucket_seconds=BUCKET_SECONDS,
            data_source=DEMO_SOURCE,
            deployment_id=deployment.id if deployment else None,
            snapshot=self.generator.batch_snapshot(),
        )
        self.samples_generated += len(requests)


demo_runtime = DemoRuntime()


# ------------------------------------------------------------------ seeding --
async def ensure_demo_registry(session: AsyncSession) -> Deployment | None:
    """Create the demo model registry and deployments if absent."""
    existing = await session.scalar(
        select(MLModel).where(MLModel.data_source == DEMO_SOURCE).limit(1)
    )
    if existing is None:
        for name, version, params, quant, context, max_batch, framework in DEMO_MODELS:
            session.add(
                MLModel(
                    name=name,
                    version=version,
                    display_name=name.replace("-", " ").title(),
                    framework=framework,
                    parameter_count_b=params,
                    quantization=quant,
                    context_length=context,
                    max_batch_size=max_batch,
                    preferred_batch_sizes="1,2,4,8,16,32",
                    description="Demo Mode model profile. Synthetic telemetry only.",
                    tags="demo",
                    data_source=DEMO_SOURCE,
                )
            )
        await session.commit()

    models = list(
        (
            await session.execute(
                select(MLModel).where(MLModel.data_source == DEMO_SOURCE).order_by(MLModel.name)
            )
        )
        .scalars()
        .all()
    )
    gpus = await telemetry_service.list_gpus(session, data_source=DEMO_SOURCE)

    existing_deployment = await session.scalar(
        select(Deployment).where(Deployment.data_source == DEMO_SOURCE).limit(1)
    )
    if existing_deployment is None and models:
        for index, model in enumerate(models):
            session.add(
                Deployment(
                    model_id=model.id,
                    name=f"{model.name}-demo",
                    environment="demo",
                    gpu_id=gpus[index % len(gpus)].id if gpus else None,
                    gpu_count=1,
                    backend="local",
                    replicas=1,
                    max_batch_size=model.max_batch_size,
                    batch_window_ms=5.0,
                    tensor_parallel_size=1,
                    status=DeploymentStatus.ACTIVE.value,
                    model_load_time_ms=18_400.0 + index * 2_100,
                    data_source=DEMO_SOURCE,
                )
            )
        await session.commit()

    return await _default_demo_deployment(session)


async def _default_demo_deployment(session: AsyncSession) -> Deployment | None:
    return (
        await session.execute(
            select(Deployment)
            .where(Deployment.data_source == DEMO_SOURCE)
            .order_by(Deployment.created_at)
            .limit(1)
        )
    ).scalar_one_or_none()


async def backfill(
    session: AsyncSession,
    *,
    minutes: int = 90,
    scenario: str | None = None,
    step_seconds: int = 60,
) -> dict[str, int]:
    """Seed historical demo telemetry so the dashboard is populated at startup.

    Writes one sample per ``step_seconds`` going back ``minutes``.
    """
    generator = DemoTelemetryGenerator(
        scenario=scenario or settings.DEMO_SCENARIO, gpu_count=settings.DEMO_GPU_COUNT
    )

    # Register devices first so metrics can attach to them.
    for device in generator.device_info():
        await telemetry_service.upsert_gpu(
            session, device, host="demo-node-01", data_source=DEMO_SOURCE
        )
    await session.commit()

    deployment = await ensure_demo_registry(session)

    # Generate on exact bucket boundaries so every aggregate covers a complete
    # interval. Straddling boundaries makes throughput depend on wall-clock
    # alignment, which is both wrong and irreproducible.
    bucket_seconds = BUCKET_SECONDS
    steps = max(1, int(minutes * 60 / bucket_seconds))
    end_bucket = floor_to_bucket(datetime.now(timezone.utc), bucket_seconds)
    first_bucket = end_bucket - timedelta(seconds=steps * bucket_seconds)

    gpu_written = 0
    request_written = 0

    for i in range(steps):
        bucket = first_bucket + timedelta(seconds=i * bucket_seconds)
        generator.advance()

        # Sample device state mid-bucket.
        sample_at = bucket + timedelta(seconds=bucket_seconds / 2)
        gpu_written += await telemetry_service.record_gpu_samples(
            session,
            generator.gpu_samples(sample_at),
            host="demo-node-01",
            data_source=DEMO_SOURCE,
        )
        await telemetry_service.record_system_sample(
            session, generator.system_sample(sample_at), data_source=DEMO_SOURCE
        )

        # Requests are laid backwards from the bucket end, so they fall inside
        # [bucket, bucket + bucket_seconds).
        requests = generator.inference_requests(
            bucket + timedelta(seconds=bucket_seconds), seconds=float(bucket_seconds)
        )
        for request in requests:
            request["deployment_id"] = deployment.id if deployment else None
            request["model_id"] = deployment.model_id if deployment else None
        request_written += await inference_service.record_requests(
            session, requests, data_source=DEMO_SOURCE
        )

        await inference_service.aggregate_bucket(
            session,
            bucket_start=bucket,
            bucket_seconds=bucket_seconds,
            data_source=DEMO_SOURCE,
            deployment_id=deployment.id if deployment else None,
        )
        await inference_service.record_batch_metric(
            session,
            bucket_start=bucket,
            bucket_seconds=bucket_seconds,
            data_source=DEMO_SOURCE,
            deployment_id=deployment.id if deployment else None,
            snapshot=generator.batch_snapshot(),
        )

    logger.info(
        "demo_backfill_complete",
        scenario=generator.scenario_key,
        minutes=minutes,
        gpu_samples=gpu_written,
        requests=request_written,
    )
    return {"gpu_samples": gpu_written, "requests": request_written, "steps": steps}


async def reset_demo_data(session: AsyncSession) -> None:
    """Remove all demo-namespace rows. Production telemetry is untouched."""
    from app.models.analytics import Alert, Anomaly, Diagnosis, Workload
    from app.models.inference import BatchMetric, InferenceMetric, InferenceRequest
    from app.models.telemetry import Gpu, GpuMetric, GpuProcess, SystemMetric

    for model in (
        InferenceRequest,
        InferenceMetric,
        BatchMetric,
        GpuMetric,
        GpuProcess,
        SystemMetric,
        Anomaly,
        Alert,
        Diagnosis,
        Workload,
        Deployment,
        MLModel,
        Gpu,
    ):
        await session.execute(delete(model).where(model.data_source == DEMO_SOURCE))
    await session.commit()
    logger.info("demo_data_reset")


def available_scenarios() -> list[str]:
    return [s.value for s in DemoScenario]
