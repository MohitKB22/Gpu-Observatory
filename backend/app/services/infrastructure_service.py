"""Snapshot of the serving infrastructure visible to the backend."""

import asyncio
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import RegisteredModel
from app.models.enums import ProviderKind
from app.monitoring.gpu_metrics import GpuReport
from app.monitoring.sampler import SystemSampler
from app.monitoring.system_metrics import read_host_metrics, read_process_metrics
from app.monitoring.vllm_metrics import VLLMServerMetrics, fetch_vllm_metrics
from app.providers.base import ProviderError
from app.schemas.infrastructure import (
    DatabaseHealthRead,
    EndpointHealthRead,
    GpuDeviceRead,
    GpuRead,
    HostRead,
    InferenceServerRead,
    InfrastructureResponse,
    UsageHistoryResponse,
    UsageSampleRead,
    WorkerRead,
)
from app.security import SecretBox
from app.services.model_service import build_endpoint_config, list_models


async def build_infrastructure(
    session: AsyncSession,
    sampler: SystemSampler,
    settings: Settings,
    http_client: httpx.AsyncClient,
    secret_box: SecretBox,
) -> InfrastructureResponse:
    sample = sampler.latest()
    host = read_host_metrics(sample.cpu_percent)
    process = read_process_metrics(sampler.process, sample.process_cpu_percent)
    models = await list_models(session)

    return InfrastructureResponse(
        sampled_at=datetime.fromtimestamp(sample.timestamp, tz=UTC),
        host=HostRead(**vars(host)),
        worker=WorkerRead(**vars(process), configured_workers=settings.web_concurrency),
        gpu=gpu_read(sampler.latest_gpu_report),
        database=await check_database(session),
        endpoints=[_endpoint_health(model) for model in models],
        inference_servers=await _scrape_vllm_servers(models, http_client, secret_box, settings),
    )


def build_usage_history(sampler: SystemSampler, interval_seconds: float) -> UsageHistoryResponse:
    return UsageHistoryResponse(
        interval_seconds=interval_seconds,
        samples=[
            UsageSampleRead(
                timestamp=datetime.fromtimestamp(sample.timestamp, tz=UTC),
                cpu_percent=sample.cpu_percent,
                memory_percent=sample.memory_percent,
                process_cpu_percent=sample.process_cpu_percent,
                gpu_utilization_percent=sample.gpu_utilization_percent,
                gpu_memory_percent=sample.gpu_memory_percent,
            )
            for sample in sampler.history()
        ],
    )


async def check_database(session: AsyncSession) -> DatabaseHealthRead:
    started = time.perf_counter()
    try:
        version = await session.scalar(text("SHOW server_version"))
    except Exception as exc:
        return DatabaseHealthRead(ok=False, latency_ms=None, server_version=None, error=type(exc).__name__)
    return DatabaseHealthRead(
        ok=True, latency_ms=(time.perf_counter() - started) * 1000, server_version=version, error=None
    )


def gpu_read(report: GpuReport | None) -> GpuRead:
    if report is None:
        return GpuRead(
            available=False, source=None, driver_version=None, devices=[], unavailable_reason="Not sampled yet."
        )
    return GpuRead(
        available=report.available,
        source=report.source,
        driver_version=report.driver_version,
        devices=[GpuDeviceRead(**vars(device)) for device in report.devices],
        unavailable_reason=report.unavailable_reason,
    )


def _endpoint_health(model: RegisteredModel) -> EndpointHealthRead:
    return EndpointHealthRead(
        model_id=model.id,
        model_name=model.name,
        provider=model.provider,
        is_demo=model.is_demo,
        is_enabled=model.is_enabled,
        status=model.status,
        last_checked_at=model.last_checked_at,
        last_check_latency_ms=model.last_check_latency_ms,
        last_error=model.last_error,
    )


async def _scrape_vllm_servers(
    models: list[RegisteredModel], http_client: httpx.AsyncClient, secret_box: SecretBox, settings: Settings
) -> list[InferenceServerRead]:
    vllm_models = [m for m in models if m.provider == ProviderKind.VLLM and m.is_enabled and m.endpoint_url]

    async def scrape(model: RegisteredModel) -> InferenceServerRead:
        try:
            api_key = build_endpoint_config(model, secret_box).api_key
            metrics = await fetch_vllm_metrics(
                http_client, model.endpoint_url, api_key, settings.vllm_metrics_timeout_seconds
            )
        except ProviderError as exc:
            metrics = VLLMServerMetrics(reachable=False, error=exc.message)
        return InferenceServerRead(model_id=model.id, model_name=model.name, **vars(metrics))

    return list(await asyncio.gather(*(scrape(model) for model in vllm_models)))
