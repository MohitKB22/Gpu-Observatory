"""Execute an inference request against a registered model and record the outcome."""

import logging
import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError
from app.models import InferenceRequest, RegisteredModel, RequestMetrics
from app.models.enums import RequestStatus
from app.monitoring.prometheus import record_inference
from app.providers.base import CompletionRequest, CompletionResult, ProviderError
from app.providers.registry import ProviderRegistry
from app.schemas.inference import InferenceCreate
from app.security import SecretBox
from app.services.model_service import build_endpoint_config

logger = logging.getLogger(__name__)


async def run_inference(
    session: AsyncSession,
    model: RegisteredModel,
    payload: InferenceCreate,
    providers: ProviderRegistry,
    secret_box: SecretBox,
    source: str,
) -> InferenceRequest:
    """Every attempt that reaches the provider is recorded, including failures, because
    failures are exactly what an observability tool needs to show."""
    if not model.is_enabled:
        raise ConflictError("This model is disabled. Enable it in the Model Registry to send requests.")

    completion_request = CompletionRequest(
        prompt=payload.prompt,
        system_prompt=payload.system_prompt,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    result: CompletionResult | None = None
    error: ProviderError | None = None
    try:
        endpoint = build_endpoint_config(model, secret_box)
        result = await providers.get(model.provider).complete(endpoint, completion_request)
    except ProviderError as exc:
        error = exc
    latency_ms = (time.perf_counter() - started) * 1000

    record = _build_record(model, payload, source, started_at, latency_ms, result, error)
    session.add(record)
    await session.commit()

    _report(record, latency_ms)
    return record


def _build_record(
    model: RegisteredModel,
    payload: InferenceCreate,
    source: str,
    started_at: datetime,
    latency_ms: float,
    result: CompletionResult | None,
    error: ProviderError | None,
) -> InferenceRequest:
    record = InferenceRequest(
        created_at=started_at,
        model_id=model.id,
        model_name=model.name,
        provider=model.provider,
        source=source,
        is_demo=model.is_demo,
        status=RequestStatus.ERROR.value if error else RequestStatus.SUCCESS.value,
        prompt=payload.prompt,
        system_prompt=payload.system_prompt,
        response_text=result.text if result else None,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        error_kind=error.kind.value if error else None,
        error_message=error.message if error else None,
        upstream_status_code=result.upstream_status_code if result else (error.status_code if error else None),
    )
    metrics = RequestMetrics(latency_ms=latency_ms)
    if result is not None:
        usage = result.usage
        metrics.prompt_tokens = usage.prompt_tokens
        metrics.completion_tokens = usage.completion_tokens
        metrics.total_tokens = usage.total_tokens
        metrics.token_count_source = usage.source.value
        # Without streaming we cannot separate time-to-first-token, so this is end-to-end
        # generation speed: completion tokens over the full request latency.
        if usage.completion_tokens and latency_ms > 0:
            metrics.tokens_per_second = usage.completion_tokens / (latency_ms / 1000)
    record.metrics = metrics
    return record


def _report(record: InferenceRequest, latency_ms: float) -> None:
    metrics = record.metrics
    record_inference(
        model=record.model_name,
        provider=record.provider,
        status=record.status,
        is_demo=record.is_demo,
        latency_seconds=latency_ms / 1000,
        prompt_tokens=metrics.prompt_tokens,
        completion_tokens=metrics.completion_tokens,
        token_count_source=metrics.token_count_source,
    )
    logger.info(
        "inference finished",
        extra={
            "request_id": str(record.id),
            "model": record.model_name,
            "provider": record.provider,
            "status": record.status,
            "demo": record.is_demo,
            "latency_ms": round(latency_ms, 1),
            "error_kind": record.error_kind,
        },
    )
