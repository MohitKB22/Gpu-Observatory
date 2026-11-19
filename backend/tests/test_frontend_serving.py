"""STATIC_DIR: the API process serves the built dashboard for single-container hosting."""

import httpx
import pytest

from app.frontend import mount_frontend
from app.main import create_app


@pytest.fixture
def built_frontend(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<!doctype html><title>shell</title>")
    (tmp_path / "assets" / "app-abc123.js").write_text("console.log('app')")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    return tmp_path


@pytest.fixture
async def static_client(settings, upstream, clean_database, built_frontend):
    application = create_app(
        settings.model_copy(update={"static_dir": str(built_frontend)}), http_transport=upstream.transport
    )
    async with application.router.lifespan_context(application):
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_client_routes_get_the_app_shell_with_security_headers(static_client):
    for path in ("/", "/models", "/logs"):
        response = await static_client.get(path)
        assert response.status_code == 200
        assert "<title>shell</title>" in response.text
        assert response.headers["cache-control"] == "no-cache"
        assert "font-src 'self' data:" in response.headers["content-security-policy"]
        assert response.headers["x-frame-options"] == "DENY"


async def test_assets_and_root_files_are_served(static_client):
    asset = await static_client.get("/assets/app-abc123.js")
    favicon = await static_client.get("/favicon.svg")

    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]
    assert favicon.text == "<svg/>"


async def test_api_routes_win_and_unknown_api_paths_stay_json_404(static_client):
    assert (await static_client.get("/api/health")).json()["status"] == "ok"

    missing = await static_client.get("/api/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


async def test_files_outside_the_build_are_never_served(static_client):
    response = await static_client.get("/..%2F..%2Fetc%2Fpasswd")

    assert response.status_code == 200
    assert "<title>shell</title>" in response.text  # falls back to the app shell


def test_missing_build_is_reported_clearly(tmp_path):
    from fastapi import FastAPI

    with pytest.raises(RuntimeError, match="index.html missing"):
        mount_frontend(FastAPI(), str(tmp_path))
