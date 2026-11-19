import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.models import HealthCheck, RegisteredModel
from app.security import SecretBox
from tests.conftest import TEST_SECRET_KEY, register_model

OPENAI_BASE = "https://llm.example.test/v1"


async def test_create_model_never_returns_api_key(client):
    created = await register_model(
        client,
        name="gpt-proxy",
        provider="openai_compatible",
        model_identifier="gpt-4o-mini",
        endpoint_url=OPENAI_BASE + "/",
        api_key="sk-test-123",
    )

    assert created["has_api_key"] is True
    assert "api_key" not in created and "encrypted_api_key" not in created
    assert created["endpoint_url"] == OPENAI_BASE  # trailing slash normalised
    assert created["status"] == "unknown"
    assert created["is_demo"] is False

    listed = (await client.get("/api/models")).json()
    assert [m["name"] for m in listed] == ["gpt-proxy"]
    assert "sk-test-123" not in (await client.get(f"/api/models/{created['id']}")).text


async def test_api_key_is_encrypted_at_rest(client, session):
    created = await register_model(
        client, name="m", provider="openai_compatible", model_identifier="x", endpoint_url=OPENAI_BASE, api_key="sk-abc"
    )
    stored = await session.get(RegisteredModel, uuid.UUID(created["id"]))

    assert stored.encrypted_api_key and "sk-abc" not in stored.encrypted_api_key
    assert SecretBox(TEST_SECRET_KEY).decrypt(stored.encrypted_api_key) == "sk-abc"


async def test_remote_provider_requires_endpoint(client):
    response = await client.post("/api/models", json={"name": "a", "provider": "vllm", "model_identifier": "m"})

    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"][0]["message"] == "endpoint_url is required for the vllm provider"


@pytest.mark.parametrize(
    "endpoint_url",
    ["ftp://host/v1", "not a url", "http://", "https://user:pass@host/v1"],
)
async def test_rejects_invalid_endpoint_urls(client, endpoint_url):
    response = await client.post(
        "/api/models",
        json={"name": "a", "provider": "openai_compatible", "model_identifier": "m", "endpoint_url": endpoint_url},
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "endpoint_url"


@pytest.mark.parametrize("timeout", [0, 601])
async def test_rejects_out_of_range_timeout(client, timeout):
    response = await client.post(
        "/api/models", json={"name": "a", "provider": "demo", "model_identifier": "m", "timeout_seconds": timeout}
    )
    assert response.status_code == 422


async def test_duplicate_name_is_a_conflict(client):
    await register_model(client, name="same")
    response = await client.post("/api/models", json={"name": "same", "provider": "demo", "model_identifier": "m"})

    assert response.status_code == 409
    assert response.json()["error"]["message"] == 'A model named "same" already exists'


async def test_partial_update_keeps_other_fields(client):
    created = await register_model(client, name="m1", description="before")

    response = await client.patch(f"/api/models/{created['id']}", json={"description": "after", "is_enabled": False})

    updated = response.json()
    assert response.status_code == 200
    assert updated["description"] == "after"
    assert updated["is_enabled"] is False
    assert updated["name"] == "m1" and updated["model_identifier"] == "orbit-8b"


async def test_changing_endpoint_resets_connection_status(client, upstream):
    upstream.on("GET", OPENAI_BASE + "/models", httpx.Response(200, json={"data": []}))
    created = await register_model(
        client, name="m", provider="openai_compatible", model_identifier="x", endpoint_url=OPENAI_BASE
    )
    await client.post(f"/api/models/{created['id']}/check")
    assert (await client.get(f"/api/models/{created['id']}")).json()["status"] == "healthy"

    response = await client.patch(f"/api/models/{created['id']}", json={"endpoint_url": "https://other.test/v1"})

    assert response.json()["status"] == "unknown"


async def test_update_can_replace_and_clear_api_key(client):
    created = await register_model(client, name="m")
    model_url = f"/api/models/{created['id']}"

    assert (await client.patch(model_url, json={"api_key": "new-key"})).json()["has_api_key"] is True
    assert (await client.patch(model_url, json={"clear_api_key": True})).json()["has_api_key"] is False


async def test_update_rejects_null_for_required_fields(client):
    created = await register_model(client, name="m")
    response = await client.patch(f"/api/models/{created['id']}", json={"name": None})

    assert response.status_code == 422


async def test_update_cannot_remove_endpoint_from_remote_model(client):
    created = await register_model(
        client, name="m", provider="openai_compatible", model_identifier="x", endpoint_url=OPENAI_BASE
    )
    response = await client.patch(f"/api/models/{created['id']}", json={"endpoint_url": None})

    assert response.status_code == 422
    assert (await client.get(f"/api/models/{created['id']}")).json()["endpoint_url"] == OPENAI_BASE


async def test_delete_model_keeps_request_history(client, session):
    created = await register_model(client, name="to-delete")
    run = (await client.post("/api/inference", json={"model_id": created["id"], "prompt": "hi"})).json()
    await client.post(f"/api/models/{created['id']}/check")

    assert (await client.delete(f"/api/models/{created['id']}")).status_code == 204

    assert (await client.get(f"/api/models/{created['id']}")).status_code == 404
    log = (await client.get(f"/api/logs/{run['id']}")).json()
    assert log["model_id"] is None and log["model_name"] == "to-delete"
    assert await session.scalar(select(func.count()).select_from(HealthCheck)) == 0


async def test_unknown_model_returns_404(client):
    response = await client.get(f"/api/models/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_connection_check_success_sends_credentials(client, upstream):
    upstream.on("GET", OPENAI_BASE + "/models", httpx.Response(200, json={"data": [{"id": "x"}]}))
    created = await register_model(
        client, name="m", provider="openai_compatible", model_identifier="x", endpoint_url=OPENAI_BASE, api_key="sk-1"
    )

    result = (await client.post(f"/api/models/{created['id']}/check")).json()

    assert result["check"]["status"] == "healthy"
    assert result["model"]["status"] == "healthy"
    assert result["model"]["last_checked_at"] is not None
    assert upstream.requests[-1].headers["Authorization"] == "Bearer sk-1"


async def test_connection_check_reports_auth_failure(client, upstream):
    upstream.on("GET", OPENAI_BASE + "/models", httpx.Response(401, json={"error": "bad key"}))
    created = await register_model(
        client, name="m", provider="openai_compatible", model_identifier="x", endpoint_url=OPENAI_BASE
    )

    result = (await client.post(f"/api/models/{created['id']}/check")).json()

    assert result["check"]["status"] == "unhealthy"
    assert result["check"]["error_kind"] == "auth"
    assert result["model"]["status"] == "unhealthy"
    assert "credentials" in result["model"]["last_error"]


async def test_connection_check_reports_unreachable_endpoint(client, upstream):
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)

    upstream.on("GET", OPENAI_BASE + "/models", refuse)
    created = await register_model(
        client, name="m", provider="openai_compatible", model_identifier="x", endpoint_url=OPENAI_BASE
    )

    check = (await client.post(f"/api/models/{created['id']}/check")).json()["check"]

    assert check["status"] == "unhealthy"
    assert check["error_kind"] == "connection"


async def test_health_check_history_is_newest_first(client):
    created = await register_model(client, name="m")
    for _ in range(3):
        await client.post(f"/api/models/{created['id']}/check")

    history = (await client.get(f"/api/models/{created['id']}/health-checks?limit=2")).json()

    assert len(history) == 2
    assert history[0]["checked_at"] >= history[1]["checked_at"]
    assert all(check["status"] == "healthy" for check in history)
