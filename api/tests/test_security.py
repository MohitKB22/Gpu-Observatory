"""Security controls: headers, limits, injection resistance, error hygiene."""

import pytest

from app.core.rbac import ROLE_SCOPES, has_scope, role_at_least, scopes_for_role, validate_scopes
from app.models.enums import Scope, UserRole


def test_role_scope_hierarchy():
    assert scopes_for_role(UserRole.VIEWER.value) < scopes_for_role(UserRole.OPERATOR.value)
    assert scopes_for_role(UserRole.OPERATOR.value) < scopes_for_role(UserRole.ADMIN.value)
    assert Scope.TELEMETRY_WRITE.value not in scopes_for_role(UserRole.VIEWER.value)
    assert Scope.ADMIN.value in scopes_for_role(UserRole.ADMIN.value)


def test_role_ordering():
    assert role_at_least("admin", "viewer")
    assert role_at_least("operator", "operator")
    assert not role_at_least("viewer", "operator")
    assert not role_at_least("nonsense-role", "viewer")


def test_admin_scope_is_a_master_key():
    assert has_scope({Scope.ADMIN.value}, Scope.TELEMETRY_WRITE.value)
    assert not has_scope({Scope.TELEMETRY_READ.value}, Scope.TELEMETRY_WRITE.value)


def test_unknown_scopes_are_rejected_not_ignored():
    with pytest.raises(ValueError):
        validate_scopes(["telemetry:read", "made-up-scope"])
    assert validate_scopes(["telemetry:read", "telemetry:read"]) == ["telemetry:read"]


def test_every_role_maps_to_known_scopes():
    valid = {s.value for s in Scope}
    for scopes in ROLE_SCOPES.values():
        assert scopes <= valid


async def test_oversized_body_is_rejected(client, admin_headers):
    response = await client.post(
        "/api/v1/agent/chat",
        headers={**admin_headers, "content-length": str(50 * 1024 * 1024)},
        json={"message": "hello gpu"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


async def test_sql_injection_in_query_params_is_harmless(client, admin_headers, seeded_demo):
    """Parameterised queries mean this returns no rows rather than executing."""
    response = await client.get(
        "/api/v1/models",
        headers=admin_headers,
        params={"source": "demo", "search": "'; DROP TABLE ml_models; --"},
    )
    assert response.status_code == 200
    assert response.json()["items"] == []

    # The table must still exist and be queryable.
    after = await client.get("/api/v1/models", headers=admin_headers, params={"source": "demo"})
    assert after.status_code == 200
    assert after.json()["meta"]["total"] > 0


async def test_path_traversal_in_identifier_is_a_clean_404(client, admin_headers):
    response = await client.get(
        "/api/v1/gpus/..%2F..%2Fetc%2Fpasswd", headers=admin_headers, params={"source": "demo"}
    )
    assert response.status_code in (404, 422)


async def test_errors_do_not_leak_internal_details(client, admin_headers):
    response = await client.get(
        "/api/v1/gpus/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
        params={"source": "demo"},
    )
    body = response.text.lower()
    for leak in ("traceback", "sqlalchemy", "/sessions/", "site-packages", "select "):
        assert leak not in body


async def test_validation_errors_do_not_echo_submitted_values(client, admin_headers):
    """A 422 must not reflect the submitted payload back to the caller."""
    secret = "super-secret-value-9f3a7c"
    response = await client.post(
        "/api/v1/models",
        headers=admin_headers,
        params={"source": "demo"},
        json={"name": "x", "framework": secret},
    )
    assert response.status_code == 422
    assert secret not in response.text


async def test_api_key_plaintext_is_never_returned_again(client, admin_headers):
    created = await client.post(
        "/api/v1/auth/api-keys",
        headers=admin_headers,
        json={"name": "one-time", "scopes": ["telemetry:read"]},
    )
    plaintext = created.json()["plaintext_key"]

    listed = await client.get("/api/v1/auth/api-keys", headers=admin_headers)
    assert plaintext not in listed.text
    assert all("plaintext" not in key for key in listed.json()["items"][0])


async def test_password_is_never_serialised(client, admin_headers):
    created = await client.post(
        "/api/v1/auth/users",
        headers=admin_headers,
        json={
            "email": "leak-check@test.local",
            "password": "another-long-password",
            "role": "viewer",
        },
    )
    assert created.status_code == 201
    assert "password" not in created.text.lower()


async def test_cors_headers_are_scoped_to_configured_origin(client, admin_headers):
    response = await client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert response.headers.get("access-control-allow-origin") != "https://evil.example.com"


def test_settings_reject_missing_secret_in_production(monkeypatch):
    """A production deployment must not start with an ephemeral secret."""
    from app.core.config import Settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "")
    monkeypatch.delenv("BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None)


def test_settings_reject_debug_in_production(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("SECRET_KEY", "a-real-secret-value-for-this-test")
    monkeypatch.setenv("DEBUG", "true")
    with pytest.raises(ValueError, match="DEBUG"):
        Settings(_env_file=None)
