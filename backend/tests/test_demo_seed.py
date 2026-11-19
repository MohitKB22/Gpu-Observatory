from sqlalchemy import func, select

from app.models import InferenceRequest, RegisteredModel
from app.services.demo_seed import (
    DEMO_MODELS,
    bootstrap_demo_data,
    ensure_demo_models,
    purge_demo_data,
    refresh_demo_history,
)
from tests.factories import add_model, add_request


async def count(session, *conditions) -> int:
    return await session.scalar(select(func.count()).select_from(InferenceRequest).where(*conditions))


async def test_bootstrap_creates_labelled_demo_data_once(app, session):
    await bootstrap_demo_data(app.state.session_factory, seed_history=True)
    await bootstrap_demo_data(app.state.session_factory, seed_history=True)

    models = list(await session.scalars(select(RegisteredModel)))
    assert sorted(m.name for m in models) == sorted(spec.name for spec in DEMO_MODELS)
    assert all(m.provider == "demo" for m in models)

    seeded = await count(session, InferenceRequest.source == "demo_seed")
    assert seeded > 500
    assert await count(session, InferenceRequest.is_demo.is_(False)) == 0
    assert await count(session, InferenceRequest.status == "error") > 0
    sample = await session.scalar(select(InferenceRequest).limit(1))
    assert sample.prompt.startswith("[Demo sample data]")


async def test_reseed_replaces_only_seeded_rows(session):
    real_model = await add_model(session, "production-model")
    await add_request(session, real_model, latency_ms=120)
    demo_models = await ensure_demo_models(session)

    first = await refresh_demo_history(session, demo_models, force=True)
    second = await refresh_demo_history(session, demo_models, force=True)

    assert first > 0 and second > 0
    assert await count(session, InferenceRequest.source == "demo_seed") == second
    assert await count(session, InferenceRequest.is_demo.is_(False)) == 1


async def test_fresh_history_is_not_regenerated(session):
    demo_models = await ensure_demo_models(session)
    await refresh_demo_history(session, demo_models, force=True)

    assert await refresh_demo_history(session, demo_models) == 0


async def test_purge_removes_demo_data_but_keeps_real_data(session):
    real_model = await add_model(session, "production-model")
    await add_request(session, real_model, latency_ms=120)
    demo_models = await ensure_demo_models(session)
    await refresh_demo_history(session, demo_models, force=True)

    await purge_demo_data(session)

    remaining = list(await session.scalars(select(RegisteredModel.name)))
    assert remaining == ["production-model"]
    assert await count(session) == 1
