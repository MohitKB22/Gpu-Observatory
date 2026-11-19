"""Demo models and labelled sample history for DEMO_MODE.

Everything created here is marked as demo data: the models use the `demo` provider and every
seeded request has is_demo=true and source='demo_seed'. Seeded rows are the only rows this
module ever deletes; real request history is never touched.
"""

import logging
import math
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import InferenceRequest, RegisteredModel, RequestMetrics
from app.models.enums import ModelStatus, ProviderKind, RequestSource, RequestStatus, TokenCountSource
from app.providers.demo import DEMO_PROFILES, DemoSpeedProfile

logger = logging.getLogger(__name__)

HISTORY_DAYS = 7
# Regenerate seeded history once it is this old, so the default 24h view is never empty.
REFRESH_AFTER = timedelta(hours=6)
SIMULATED_TIMEOUT_MS = 60_000.0


@dataclass(frozen=True)
class DemoModelSpec:
    name: str
    identifier: str
    description: str
    requests_per_hour: float
    error_rate: float


DEMO_MODELS = (
    DemoModelSpec(
        "demo-swift-1b", "swift-1b", "Simulated small, fast model (local demo provider, no real inference).", 40, 0.012
    ),
    DemoModelSpec(
        "demo-orbit-8b", "orbit-8b", "Simulated mid-size model (local demo provider, no real inference).", 25, 0.02
    ),
    DemoModelSpec(
        "demo-atlas-70b",
        "atlas-70b",
        "Simulated large, slower model (local demo provider, no real inference).",
        10,
        0.035,
    ),
)

SAMPLE_PROMPTS = (
    "Summarise the attached incident report in three bullet points.",
    "Write a SQL query that returns the top 10 customers by revenue this quarter.",
    "Explain the difference between P95 and P99 latency to a product manager.",
    "Translate this support reply into Spanish, keeping a friendly tone.",
    "Classify the sentiment of this review: 'Setup took five minutes and it just works.'",
    "Draft a commit message for a change that adds retry logic to the HTTP client.",
    "Extract the invoice number, date and total from the following text.",
    "Suggest three names for an internal analytics dashboard.",
    "Rewrite this paragraph to be more concise without losing detail.",
    "What are common causes of GPU out-of-memory errors during inference?",
)


async def bootstrap_demo_data(session_factory: async_sessionmaker[AsyncSession], seed_history: bool) -> None:
    async with session_factory() as session:
        models = await ensure_demo_models(session)
        if seed_history:
            await refresh_demo_history(session, models)


async def ensure_demo_models(session: AsyncSession) -> list[RegisteredModel]:
    names = [spec.name for spec in DEMO_MODELS]
    existing = {m.name: m for m in await session.scalars(_demo_models_query(names))}
    missing = [spec for spec in DEMO_MODELS if spec.name not in existing]
    if missing:
        for spec in missing:
            session.add(
                RegisteredModel(
                    name=spec.name,
                    provider=ProviderKind.DEMO.value,
                    model_identifier=spec.identifier,
                    description=spec.description,
                    timeout_seconds=60,
                    is_enabled=True,
                    status=ModelStatus.UNKNOWN.value,
                )
            )
        try:
            await session.commit()
        except IntegrityError:
            # Another worker created them first.
            await session.rollback()
        existing = {m.name: m for m in await session.scalars(_demo_models_query(names))}
    return [existing[name] for name in names if name in existing]


async def refresh_demo_history(session: AsyncSession, models: list[RegisteredModel], force: bool = False) -> int:
    """Replace seeded history if it is missing or stale. Returns the number of rows inserted."""
    now = datetime.now(UTC)
    newest = await session.scalar(
        select(func.max(InferenceRequest.created_at)).where(InferenceRequest.source == RequestSource.DEMO_SEED.value)
    )
    if not force and newest is not None and now - newest < REFRESH_AFTER:
        return 0

    # request_metrics rows are removed by the ON DELETE CASCADE foreign key.
    await session.execute(delete(InferenceRequest).where(InferenceRequest.source == RequestSource.DEMO_SEED.value))
    requests, metrics = generate_demo_history(models, now, random.Random(now.toordinal()))
    if requests:
        await session.execute(insert(InferenceRequest), requests)
        await session.execute(insert(RequestMetrics), metrics)
    await session.commit()
    logger.info("seeded demo request history", extra={"rows": len(requests)})
    return len(requests)


async def purge_demo_data(session: AsyncSession) -> None:
    """Remove every demo record: demo models, their health checks and all demo requests."""
    await session.execute(delete(InferenceRequest).where(InferenceRequest.is_demo.is_(True)))
    await session.execute(delete(RegisteredModel).where(RegisteredModel.provider == ProviderKind.DEMO.value))
    await session.commit()


def _demo_models_query(names: list[str]):
    return select(RegisteredModel).where(
        RegisteredModel.name.in_(names), RegisteredModel.provider == ProviderKind.DEMO.value
    )


def generate_demo_history(
    models: list[RegisteredModel], now: datetime, rng: random.Random
) -> tuple[list[dict], list[dict]]:
    specs = {spec.name: spec for spec in DEMO_MODELS}
    requests: list[dict] = []
    metrics: list[dict] = []
    start = now - timedelta(days=HISTORY_DAYS)

    for model in models:
        spec = specs.get(model.name)
        if spec is None:
            continue
        profile = DEMO_PROFILES.get(model.model_identifier, DEMO_PROFILES["orbit-8b"])
        hour = start
        while hour < now:
            # Older days are thinner so the 24h view has more detail than the 7d view.
            volume = 1.0 if now - hour <= timedelta(hours=24) else 0.35
            count = round(spec.requests_per_hour * volume * _daily_traffic_shape(hour) * rng.uniform(0.8, 1.2))
            for _ in range(count):
                created_at = hour + timedelta(seconds=rng.uniform(0, 3600))
                if created_at >= now:
                    continue
                request, metric = _simulated_request(model, spec, profile, created_at, now, rng)
                requests.append(request)
                metrics.append(metric)
            hour += timedelta(hours=1)
    return requests, metrics


def _daily_traffic_shape(moment: datetime) -> float:
    """Busier during the (UTC) working day, quieter overnight."""
    return 0.55 + 0.45 * math.sin((moment.hour - 6) / 24 * 2 * math.pi)


def _simulated_request(
    model: RegisteredModel,
    spec: DemoModelSpec,
    profile: DemoSpeedProfile,
    created_at: datetime,
    now: datetime,
    rng: random.Random,
) -> tuple[dict, dict]:
    request_id = uuid.uuid4()
    prompt = rng.choice(SAMPLE_PROMPTS)
    prompt_tokens = _clamp(int(rng.lognormvariate(4.5, 0.7)), 8, 3000)
    completion_tokens = _clamp(int(rng.lognormvariate(5.0, 0.6)), 16, 1024)

    # A short simulated incident on the largest model three to four hours ago gives the
    # error and latency charts something realistic to show.
    in_incident = spec.identifier == "atlas-70b" and timedelta(hours=3) <= now - created_at <= timedelta(hours=4)
    error_rate = 0.25 if in_incident else spec.error_rate

    request = {
        "id": request_id,
        "created_at": created_at,
        "model_id": model.id,
        "model_name": model.name,
        "provider": model.provider,
        "source": RequestSource.DEMO_SEED.value,
        "is_demo": True,
        "prompt": f"[Demo sample data] {prompt}",
        "system_prompt": None,
        "temperature": rng.choice((0.0, 0.2, 0.7, 1.0)),
        "max_tokens": rng.choice((256, 512, 1024)),
        "response_text": None,
        "error_kind": None,
        "error_message": None,
        "upstream_status_code": None,
    }

    if rng.random() < error_rate:
        timed_out = rng.random() < 0.6
        latency_ms = SIMULATED_TIMEOUT_MS if timed_out else rng.uniform(80, 400)
        request.update(
            status=RequestStatus.ERROR.value,
            error_kind="timeout" if timed_out else "http",
            error_message=(
                "No response from the endpoint within 60s (simulated)"
                if timed_out
                else "Endpoint returned HTTP 503: model overloaded (simulated)"
            ),
            upstream_status_code=None if timed_out else 503,
        )
        metric = {"request_id": request_id, "latency_ms": latency_ms}
        return request, _with_empty_tokens(metric)

    latency_ms = (profile.base_latency_ms + completion_tokens / profile.tokens_per_second * 1000) * rng.lognormvariate(
        0, 0.18
    )
    if in_incident or rng.random() < 0.03:
        latency_ms *= rng.uniform(1.8, 3.5)  # slow tail
    request.update(
        status=RequestStatus.SUCCESS.value,
        response_text=(
            f"[Demo sample data] Simulated completion of {completion_tokens} tokens. No model generated this text."
        ),
        upstream_status_code=200,
    )
    metric = {
        "request_id": request_id,
        "latency_ms": latency_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "token_count_source": TokenCountSource.ESTIMATED.value,
        "tokens_per_second": completion_tokens / (latency_ms / 1000),
    }
    return request, metric


def _with_empty_tokens(metric: dict) -> dict:
    return metric | {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
        "token_count_source": None,
        "tokens_per_second": None,
    }


def _clamp(value: int, lowest: int, highest: int) -> int:
    return max(lowest, min(highest, value))
