"""Authentication, authorisation and API-key behaviour."""

import pytest

from app.core.security import (
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("a-sufficiently-long-password")
    assert hashed != "a-sufficiently-long-password"
    assert verify_password("a-sufficiently-long-password", hashed)
    assert not verify_password("wrong-password-entirely", hashed)


def test_short_passwords_are_rejected():
    with pytest.raises(ValueError):
        hash_password("short")


def test_api_key_hash_is_deterministic_and_not_the_plaintext():
    plaintext, prefix, digest = generate_api_key()
    assert plaintext.startswith(prefix)
    assert digest != plaintext
    assert hash_api_key(plaintext) == digest


async def test_login_returns_token_pair(client, admin_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.local", "password": "test-password-1234"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    payload = decode_token(body["access_token"], expected_type="access")
    assert payload["role"] == "admin"


async def test_login_with_bad_password_is_rejected(client, admin_user):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.local", "password": "definitely-wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_unknown_and_known_accounts_give_identical_errors(client, admin_user):
    """The login endpoint must not allow account enumeration."""
    unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@test.local", "password": "definitely-wrong-password"},
    )
    known = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.local", "password": "definitely-wrong-password"},
    )
    assert unknown.status_code == known.status_code == 401
    assert unknown.json()["error"]["message"] == known.json()["error"]["message"]


async def test_protected_route_requires_credentials(client):
    response = await client.get("/api/v1/gpus")
    assert response.status_code == 401


async def test_invalid_token_is_rejected(client):
    response = await client.get(
        "/api/v1/gpus", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert response.status_code == 401


async def test_me_returns_current_user(client, admin_headers):
    response = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "admin@test.local"


async def test_viewer_cannot_create_models(client, viewer_headers):
    """RBAC: viewers hold no write scope."""
    response = await client.post(
        "/api/v1/models", headers=viewer_headers, json={"name": "blocked-model"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_viewer_cannot_list_users(client, viewer_headers):
    response = await client.get("/api/v1/auth/users", headers=viewer_headers)
    assert response.status_code == 403


async def test_admin_can_create_and_revoke_api_key(client, admin_headers):
    created = await client.post(
        "/api/v1/auth/api-keys",
        headers=admin_headers,
        json={"name": "telemetry-agent", "scopes": ["telemetry:read", "telemetry:write"]},
    )
    assert created.status_code == 201
    body = created.json()
    plaintext = body["plaintext_key"]
    assert plaintext.startswith("nvo_")

    # The API key authenticates just like a JWT.
    used = await client.get("/api/v1/gpus", headers={"Authorization": f"Bearer {plaintext}"})
    assert used.status_code == 200

    revoked = await client.delete(
        f"/api/v1/auth/api-keys/{body['api_key']['id']}", headers=admin_headers
    )
    assert revoked.status_code == 200
    assert revoked.json()["is_active"] is False

    after = await client.get("/api/v1/gpus", headers={"Authorization": f"Bearer {plaintext}"})
    assert after.status_code == 401


async def test_api_key_scopes_are_enforced(client, admin_headers):
    created = await client.post(
        "/api/v1/auth/api-keys",
        headers=admin_headers,
        json={"name": "read-only-agent", "scopes": ["telemetry:read"]},
    )
    key = created.json()["plaintext_key"]
    headers = {"Authorization": f"Bearer {key}"}

    assert (await client.get("/api/v1/gpus", headers=headers)).status_code == 200
    blocked = await client.post(
        "/api/v1/models", headers=headers, json={"name": "should-be-blocked"}
    )
    assert blocked.status_code == 403


async def test_unknown_scope_is_rejected(client, admin_headers):
    response = await client.post(
        "/api/v1/auth/api-keys",
        headers=admin_headers,
        json={"name": "bad", "scopes": ["telemetry:read", "not-a-real-scope"]},
    )
    assert response.status_code == 422


async def test_refresh_rotates_and_revokes(client, admin_user):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.local", "password": "test-password-1234"},
    )
    refresh_token = login.json()["refresh_token"]

    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert rotated.status_code == 200
    assert rotated.json()["refresh_token"] != refresh_token

    # Re-using the old token must fail: it was revoked on rotation.
    reused = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert reused.status_code == 401


async def test_audit_log_records_login(client, admin_headers):
    response = await client.get("/api/v1/auth/audit", headers=admin_headers)
    assert response.status_code == 200
    actions = {item["action"] for item in response.json()["items"]}
    assert "auth.login" in actions
