"""Synthetic workload execution.

Drives real requests through the configured inference adapter and records the
observed timings, so the diagnostics engine is exercised against measurements
rather than invented numbers.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.logging import get_logger
from app.core.timerange import floor_to_bucket
from app.inference.adapters import InferenceRequestSpec, build_adapter
from app.models.analytics import Workload
from app.models.enums import DataSource, WorkloadProfile, WorkloadStatus
from app.services import inference_service

logger = get_logger(__name__)

BUCKET_SECONDS = 60

# profile -> (concurrency, batch_size, prompt_tokens, target_rps)
PROFILE_DEFAULTS: dict[str, tuple[int, int, int, float]] = {
    WorkloadProfile.LOW_CONCURRENCY.value: (2, 1, 64, 4.0),
    WorkloadProfile.HIGH_CONCURRENCY.value: (48, 16, 96, 40.0),
    WorkloadProfile.SMALL_BATCH.value: (4, 1, 64, 8.0),
    WorkloadProfile.LARGE_BATCH.value: (32, 32, 128, 24.0),
    WorkloadProfile.LATENCY_SPIKE.value: (16, 4, 1024, 10.0),
    WorkloadProfile.MEMORY_PRESSURE.value: (24, 8, 4096, 12.0),
}


async def run_workload(maker: async_sessionmaker[AsyncSession], workload_id: str) -> None:
    """Execute a workload to completion, recording telemetry as it goes."""
    adapter = build_adapter()
    try:
        async with maker() as session:
            workload = await session.scalar(select(Workload).where(Workload.id == workload_id))
            if workload is None:
                logger.warning("workload_missing", workload_id=workload_id)
                return
            defaults = PROFILE_DEFAULTS.get(
                workload.profile, PROFILE_DEFAULTS[WorkloadProfile.LOW_CONCURRENCY.value]
            )
            concurrency = workload.concurrency or defaults[0]
            batch_size = workload.batch_size or defaults[1]
            prompt_tokens = defaults[2]
            target_rps = workload.target_rps or defaults[3]
            duration = workload.duration_seconds or 60
            deployment_id = workload.deployment_id

            workload.status = WorkloadStatus.RUNNING.value
            workload.started_at = datetime.now(timezone.utc)
            await session.commit()

        prompt = "benchmark " * max(1, prompt_tokens // 2)
        deadline = time.monotonic() + duration
        semaphore = asyncio.Semaphore(max(1, concurrency))
        pending: list[dict] = []
        generated = 0
        errors = 0
        # Pace request submission toward the requested rate.
        interval = 1.0 / max(0.1, target_rps)

        async def one_request() -> dict:
            async with semaphore:
                result = await adapter.infer(
                    InferenceRequestSpec(prompt=prompt, model="workload", max_tokens=64)
                )
            return {
                "deployment_id": deployment_id,
                "started_at": datetime.now(timezone.utc),
                "total_latency_ms": result.total_latency_ms,
                "queue_latency_ms": result.queue_latency_ms,
                "preprocess_latency_ms": result.preprocess_latency_ms,
                "execution_latency_ms": result.execution_latency_ms,
                "postprocess_latency_ms": result.postprocess_latency_ms,
                "time_to_first_token_ms": result.time_to_first_token_ms,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "batch_size": batch_size,
                "concurrency": concurrency,
                "status_code": result.status_code,
                "is_error": result.is_error,
                "error_type": result.error_type,
                "client_id": "workload-generator",
            }

        tasks: set[asyncio.Task] = set()
        while time.monotonic() < deadline:
            async with maker() as session:
                current = await session.scalar(
                    select(Workload.status).where(Workload.id == workload_id)
                )
            if current == WorkloadStatus.CANCELLED.value:
                logger.info("workload_cancelled", workload_id=workload_id)
                break

            for _ in range(max(1, int(target_rps / 10))):
                task = asyncio.create_task(one_request())
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            await asyncio.sleep(max(0.01, interval * max(1, int(target_rps / 10))))

            done = [t for t in list(tasks) if t.done()]
            for task in done:
                try:
                    pending.append(task.result())
                except Exception:
                    errors += 1

            if len(pending) >= 200:
                async with maker() as session:
                    generated += await inference_service.record_requests(
                        session, pending, data_source=DataSource.DEMO.value
                    )
                pending.clear()

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for item in results:
                if isinstance(item, dict):
                    pending.append(item)
                else:
                    errors += 1

        async with maker() as session:
            if pending:
                generated += await inference_service.record_requests(
                    session, pending, data_source=DataSource.DEMO.value
                )
            bucket = floor_to_bucket(datetime.now(timezone.utc), BUCKET_SECONDS)
            await inference_service.aggregate_bucket(
                session,
                bucket_start=bucket,
                bucket_seconds=BUCKET_SECONDS,
                data_source=DataSource.DEMO.value,
                deployment_id=deployment_id,
            )
            await inference_service.record_batch_metric(
                session,
                bucket_start=bucket,
                bucket_seconds=BUCKET_SECONDS,
                data_source=DataSource.DEMO.value,
                deployment_id=deployment_id,
                snapshot={
                    "requested_batch_size": float(batch_size),
                    "effective_batch_size": float(batch_size),
                    "avg_batch_size": float(batch_size),
                    "max_batch_size": batch_size,
                    "configured_max_batch_size": max(batch_size, 32),
                    "queue_depth": float(concurrency),
                    "batch_efficiency": round(batch_size / max(batch_size, 32), 4),
                    "throughput_rps": round(generated / max(1, duration), 3),
                },
            )

            workload = await session.scalar(select(Workload).where(Workload.id == workload_id))
            if workload is not None and workload.status != WorkloadStatus.CANCELLED.value:
                workload.status = WorkloadStatus.COMPLETED.value
            if workload is not None:
                workload.finished_at = datetime.now(timezone.utc)
                workload.requests_generated = generated
                workload.errors_generated = errors
            await session.commit()

        logger.info("workload_complete", workload_id=workload_id, requests=generated, errors=errors)
    except Exception as exc:
        logger.exception("workload_failed", workload_id=workload_id, error=str(exc)[:200])
        try:
            async with maker() as session:
                workload = await session.scalar(select(Workload).where(Workload.id == workload_id))
                if workload is not None:
                    workload.status = WorkloadStatus.FAILED.value
                    workload.finished_at = datetime.now(timezone.utc)
                    workload.error_message = str(exc)[:2000]
                    await session.commit()
        except Exception:
            pass
    finally:
        await adapter.close()
