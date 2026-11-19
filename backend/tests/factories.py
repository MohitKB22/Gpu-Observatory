"""Insert request records with controlled values, for analytics and log tests."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InferenceRequest, RegisteredModel, RequestMetrics


async def add_model(session: AsyncSession, name: str, provider: str = "openai_compatible") -> RegisteredModel:
    model = RegisteredModel(
        name=name,
        provider=provider,
        model_identifier=name,
        endpoint_url=None if provider == "demo" else "https://example.test/v1",
        timeout_seconds=60,
        is_enabled=True,
        status="unknown",
    )
    session.add(model)
    await session.commit()
    return model


async def add_request(
    session: AsyncSession,
    model: RegisteredModel,
    *,
    latency_ms: float,
    status: str = "success",
    minutes_ago: float = 5,
    prompt: str = "test prompt",
    response_text: str | None = "test response",
    error_message: str | None = None,
    prompt_tokens: int | None = 10,
    completion_tokens: int | None = 20,
    token_count_source: str | None = "exact",
    source: str = "api",
) -> InferenceRequest:
    succeeded = status == "success"
    request = InferenceRequest(
        id=uuid.uuid4(),
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        model_id=model.id,
        model_name=model.name,
        provider=model.provider,
        source=source,
        is_demo=model.is_demo,
        status=status,
        prompt=prompt,
        response_text=response_text if succeeded else None,
        temperature=0.7,
        max_tokens=256,
        error_kind=None if succeeded else "http",
        error_message=None if succeeded else (error_message or "Endpoint returned HTTP 500"),
    )
    request.metrics = RequestMetrics(
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens if succeeded else None,
        completion_tokens=completion_tokens if succeeded else None,
        total_tokens=(prompt_tokens + completion_tokens) if succeeded and prompt_tokens is not None else None,
        token_count_source=token_count_source if succeeded else None,
        tokens_per_second=(completion_tokens / (latency_ms / 1000)) if succeeded and completion_tokens else None,
    )
    session.add(request)
    await session.commit()
    return request
