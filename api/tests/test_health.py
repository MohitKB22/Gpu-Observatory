"""Health, readiness, metrics and OpenAPI."""


async def test_health_returns_ok(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert "uptime_seconds" in body


async def test_ready_reports_components(client):
    response = await client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    names = {c["name"] for c in body["components"]}
    assert {"database", "cache"} <= names
    assert all(c["latency_ms"] is not None for c in body["components"])


async def test_metrics_is_prometheus_format(client):
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "nvo_http_requests_total" in response.text
    assert "nvo_telemetry_samples_total" in response.text


async def test_openapi_document_is_valid(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"]
    assert "BearerAuth" in schema["components"]["securitySchemes"]
    # Spot-check that the endpoints the specification requires are documented.
    for path in (
        "/api/v1/gpus",
        "/api/v1/models",
        "/api/v1/inference/metrics",
        "/api/v1/comparisons/models",
        "/api/v1/batches",
        "/api/v1/anomalies",
        "/api/v1/alerts",
        "/api/v1/cost",
        "/api/v1/diagnostics",
        "/api/v1/diagnostics/history",
        "/api/v1/agent/chat",
    ):
        assert path in schema["paths"], f"missing documented endpoint: {path}"


async def test_request_id_header_is_returned(client):
    response = await client.get("/health")
    assert response.headers.get("X-Request-ID")


async def test_request_id_is_propagated(client):
    response = await client.get("/health", headers={"X-Request-ID": "trace-abc-12345"})
    assert response.headers["X-Request-ID"] == "trace-abc-12345"


async def test_security_headers_present(client):
    response = await client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "Content-Security-Policy" in response.headers


async def test_root_lists_entrypoints(client):
    body = (await client.get("/")).json()
    assert body["docs"] == "/docs"
    assert body["api"] == "/api/v1"


async def test_unknown_route_uses_error_envelope(client):
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_logging_configuration_emits_at_info(capsys):
    """Regression guard: the processor chain must match the logger factory.

    A stdlib-only processor (add_logger_name) paired with a non-stdlib factory
    raises on the first INFO record, which crashes application startup while
    leaving a WARNING-level test suite green.
    """
    from app.core.logging import configure_logging, get_logger

    configure_logging("INFO", "json")
    logger = get_logger("test.logging")
    logger.info("startup_probe", detail="value")

    captured = capsys.readouterr()
    assert "startup_probe" in captured.out
    assert "test.logging" in captured.out
    configure_logging("WARNING", "console")
