"""Background workers: telemetry collection, aggregation, analytics, retention.

Each worker owns its own session and is defensive: a failure in one cycle is
logged and the loop continues, because an observability platform that stops
observing on the first error is worse than useless.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collectors.dcgm import DcgmCollector
from app.collectors.nvml import NvmlCollector
from app.collectors.system import SystemCollector
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import (
    RETENTION_ROWS_DELETED,
    TELEMETRY_COLLECT_LATENCY,
    TELEMETRY_FAILURES,
    TELEMETRY_LAST_SUCCESS,
)
from app.core.timerange import floor_to_bucket
from app.models.enums import DataSource
from app.realtime.manager import manager
from app.services import alert_service, anomaly_service, inference_service, telemetry_service

logger = get_logger(__name__)

BUCKET_SECONDS = 60


class WorkerSupervisor:
    """Owns the lifecycle of every background loop."""

    def __init__(self) -> None:
        self._tasks: list[asyncio.Task] = []
        self._running = False
        self.nvml: NvmlCollector | None = None
        self.dcgm: DcgmCollector | None = None
        self.system: SystemCollector | None = None
        self._maker: async_sessionmaker[AsyncSession] | None = None

    @property
    def running(self) -> bool:
        return self._running

    async def start(self, maker: async_sessionmaker[AsyncSession]) -> None:
        if self._running:
            return
        self._maker = maker
        self._running = True

        if settings.GPU_METRICS_ENABLED:
            self.nvml = NvmlCollector()
            if settings.DCGM_ENABLED:
                self.dcgm = DcgmCollector()
        if settings.SYSTEM_METRICS_ENABLED:
            self.system = SystemCollector()

        if settings.TELEMETRY_ENABLED:
            self._spawn(self._telemetry_loop(), "telemetry-collector")
            self._spawn(self._aggregation_loop(), "aggregation")
            self._spawn(self._analytics_loop(), "analytics")
        self._spawn(self._retention_loop(), "retention")
        logger.info("workers_started", count=len(self._tasks))

    def _spawn(self, coro, name: str) -> None:
        self._tasks.append(asyncio.create_task(coro, name=name))

    async def stop(self) -> None:
        self._running = False
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks.clear()
        if self.nvml:
            self.nvml.shutdown()
        logger.info("workers_stopped")

    # ------------------------------------------------------------ telemetry --
    async def _telemetry_loop(self) -> None:
        assert self._maker is not None
        interval = max(1.0, settings.TELEMETRY_INTERVAL_SECONDS)
        registered = False

        while self._running:
            started = time.perf_counter()
            try:
                async with self._maker() as session:
                    if not registered:
                        registered = await self._register_devices(session)
                    await self._collect_once(session)
                TELEMETRY_LAST_SUCCESS.labels(kind="production").set(time.time())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                TELEMETRY_FAILURES.labels(kind="production", reason="collect_error").inc()
                logger.exception("telemetry_cycle_failed", error=str(exc)[:200])
            finally:
                TELEMETRY_COLLECT_LATENCY.labels(kind="production").observe(
                    time.perf_counter() - started
                )
            await asyncio.sleep(interval)

    async def _register_devices(self, session: AsyncSession) -> bool:
        devices = []
        if self.nvml and self.nvml.status().available:
            devices = self.nvml.discover()
        elif self.dcgm:
            devices = self.dcgm.discover()
        for device in devices:
            await telemetry_service.upsert_gpu(
                session, device, data_source=DataSource.PRODUCTION.value
            )
        if devices:
            await session.commit()
            logger.info("gpu_devices_registered", count=len(devices))
        return True

    async def _collect_once(self, session: AsyncSession) -> None:
        samples = []
        if self.nvml and self.nvml.status().available:
            samples = self.nvml.sample()
        elif self.dcgm:
            samples = self.dcgm.sample()

        if samples:
            await telemetry_service.record_gpu_samples(
                session, samples, data_source=DataSource.PRODUCTION.value
            )
            await manager.broadcast(
                "telemetry",
                {
                    "kind": "gpu",
                    "samples": [
                        {
                            "uuid": s.uuid,
                            "index": s.index,
                            "utilization_pct": s.utilization_pct,
                            "memory_utilization_pct": s.memory_utilization_pct,
                            "temperature_c": s.temperature_c,
                            "power_w": s.power_w,
                        }
                        for s in samples
                    ],
                },
                data_source=DataSource.PRODUCTION.value,
            )

        if self.system and self.system.status().available:
            sample = self.system.sample()
            if sample:
                await telemetry_service.record_system_sample(
                    session, sample, data_source=DataSource.PRODUCTION.value
                )
                await manager.broadcast(
                    "telemetry",
                    {
                        "kind": "system",
                        "cpu_utilization_pct": sample.cpu_utilization_pct,
                        "ram_utilization_pct": sample.ram_utilization_pct,
                        "host": sample.host,
                    },
                    data_source=DataSource.PRODUCTION.value,
                )

    # ---------------------------------------------------------- aggregation --
    async def _aggregation_loop(self) -> None:
        assert self._maker is not None
        while self._running:
            await asyncio.sleep(BUCKET_SECONDS)
            try:
                async with self._maker() as session:
                    bucket = floor_to_bucket(datetime.now(timezone.utc), BUCKET_SECONDS)
                    for source in self._active_sources():
                        deployment = await inference_service.resolve_default_deployment(
                            session, data_source=source
                        )
                        await inference_service.aggregate_bucket(
                            session,
                            bucket_start=bucket,
                            bucket_seconds=BUCKET_SECONDS,
                            data_source=source,
                            deployment_id=deployment.id if deployment else None,
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("aggregation_cycle_failed", error=str(exc)[:200])

    # ------------------------------------------------------------ analytics --
    async def _analytics_loop(self) -> None:
        assert self._maker is not None
        while self._running:
            await asyncio.sleep(60)
            try:
                async with self._maker() as session:
                    for source in self._active_sources():
                        anomalies = await anomaly_service.scan(session, data_source=source)
                        if anomalies:
                            await manager.broadcast(
                                "diagnostics",
                                {
                                    "kind": "anomalies",
                                    "count": len(anomalies),
                                    "items": [
                                        {
                                            "metric_kind": a.metric_kind,
                                            "severity": a.severity,
                                            "description": a.description,
                                        }
                                        for a in anomalies[:5]
                                    ],
                                },
                                data_source=source,
                            )
                        fired = await alert_service.evaluate(session, data_source=source)
                        if fired:
                            await manager.broadcast(
                                "alerts",
                                {
                                    "kind": "fired",
                                    "count": len(fired),
                                    "items": [
                                        {
                                            "id": a.id,
                                            "title": a.title,
                                            "severity": a.severity,
                                            "observed_value": a.observed_value,
                                        }
                                        for a in fired
                                    ],
                                },
                                data_source=source,
                            )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("analytics_cycle_failed", error=str(exc)[:200])

    # ------------------------------------------------------------ retention --
    async def _retention_loop(self) -> None:
        assert self._maker is not None
        interval = max(300, settings.RETENTION_SWEEP_INTERVAL_SECONDS)
        while self._running:
            await asyncio.sleep(interval)
            try:
                async with self._maker() as session:
                    deleted = await telemetry_service.purge_expired(session)
                for table, count in deleted.items():
                    if count:
                        RETENTION_ROWS_DELETED.labels(table=table).inc(count)
                if any(deleted.values()):
                    logger.info("retention_sweep", **deleted)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("retention_cycle_failed", error=str(exc)[:200])

    @staticmethod
    def _active_sources() -> list[str]:
        sources = [DataSource.PRODUCTION.value]
        if settings.DEMO_MODE:
            sources.append(DataSource.DEMO.value)
        return sources

    # -------------------------------------------------------------- status ---
    def collector_status(self) -> dict[str, dict]:
        return {
            "nvml": {
                "available": self.nvml.status().available if self.nvml else False,
                "reason": self.nvml.status().reason if self.nvml else "disabled",
            },
            "dcgm": {
                "available": self.dcgm.status().available if self.dcgm else False,
                "reason": self.dcgm.status().reason if self.dcgm else "disabled",
            },
            "system": {
                "available": self.system.status().available if self.system else False,
                "reason": self.system.status().reason if self.system else "disabled",
            },
        }


supervisor = WorkerSupervisor()
