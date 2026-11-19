"""PUBLIC_DEMO: read-only registry, demo-only inference with limits, and bounded storage."""

import httpx
import pytest
from sqlalchemy import func, select

from app.main import create_app
from app.models import InferenceRequest
from tests.factories import add_model, add_request


@pytest.fixture
def public_settings(settings):
    return settings.model_copy(
        update={
            "public_demo": True,
            "public_demo_source_url": "https://github.com/example/observatory",
            "public_demo_requests_per_minute": 3,
            "public_demo_max_prompt_chars": 50,
            "public_demo_max_tokens": 64,
        }
    )


@pytest.fixture
async def public_app(public_settings, upstream, clean_database):
    application = create_app(public_settings, http_transport=upstream.transport)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def public_client(public_app):
    transport = httpx.ASGITransport(app=public_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
async def models(public_app):
    async with public_app.state.session_factory() as session:
        demo = await add_model(session, "demo-public", provider="demo")
        real = await add_model(session, "real-private")
        return demo, real


async def test_system_info_announces_public_demo(public_client):
    info = (await public_client.get("/api/system/info")).json()

    assert info["public_demo"] is True
    assert info["public_demo_source_url"] == "https://github.com/example/observatory"
    assert (info["max_prompt_chars"], info["max_tokens"]) == (50, 64)


async def test_registry_is_read_only(public_client, models):
    demo, _ = models

    created = await public_client.post("/api/models", json={"name": "x", "provider": "demo", "model_identifier": "m"})
    updated = await public_client.patch(f"/api/models/{demo.id}", json={"is_enabled": False})
    deleted = await public_client.delete(f"/api/models/{demo.id}")

    for response in (created, updated, deleted):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "forbidden"
    assert (await public_client.get("/api/models")).status_code == 200


async def test_demo_models_can_still_be_run_and_checked(public_client, models):
    demo, _ = models

    run = await public_client.post(
        "/api/inference", json={"model_id": str(demo.id), "prompt": "hello", "max_tokens": 32}
    )
    check = await public_client.post(f"/api/models/{demo.id}/check")

    assert run.status_code == 200 and run.json()["is_demo"] is True
    assert check.json()["check"]["status"] == "healthy"


async def test_only_demo_models_can_be_run(public_client, models):
    _, real = models

    response = await public_client.post("/api/inference", json={"model_id": str(real.id), "prompt": "hello"})

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("overrides", "message"), [({"prompt": "x" * 51}, "50 characters"), ({"max_tokens": 65}, "64")]
)
async def test_input_limits_are_tighter(public_client, models, overrides, message):
    demo, _ = models
    payload = {"model_id": str(demo.id), "prompt": "hello", "max_tokens": 32} | overrides

    response = await public_client.post("/api/inference", json=payload)

    assert response.status_code == 422
    assert message in response.json()["error"]["message"]


async def test_visitors_are_rate_limited(public_client, models):
    demo, _ = models
    payload = {"model_id": str(demo.id), "prompt": "hello", "max_tokens": 16}

    statuses = [(await public_client.post("/api/inference", json=payload)).status_code for _ in range(4)]

    assert statuses == [200, 200, 200, 429]


async def test_stored_visitor_runs_are_capped(public_settings, upstream, clean_database):
    settings = public_settings.model_copy(
        update={"public_demo_kept_requests": 2, "public_demo_requests_per_minute": 50}
    )
    application = create_app(settings, http_transport=upstream.transport)
    async with application.router.lifespan_context(application):
        async with application.state.session_factory() as session:
            demo = await add_model(session, "demo-public", provider="demo")
            real = await add_model(session, "real-private")
            await add_request(session, real, latency_ms=100)  # real history must survive
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(5):
                payload = {"model_id": str(demo.id), "prompt": "hi", "max_tokens": 8, "source": "playground"}
                assert (await client.post("/api/inference", json=payload)).status_code == 200

        async with application.state.session_factory() as session:
            playground = await session.scalar(
                select(func.count()).select_from(InferenceRequest).where(InferenceRequest.source == "playground")
            )
            real_rows = await session.scalar(
                select(func.count()).select_from(InferenceRequest).where(InferenceRequest.is_demo.is_(False))
            )

    assert playground == 2
    assert real_rows == 1
