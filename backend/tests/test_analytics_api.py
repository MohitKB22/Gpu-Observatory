import pytest

from tests.factories import add_model, add_request


@pytest.fixture
async def recorded_traffic(session):
    """Real model: 10 successes at 100..1000 ms plus 2 errors. Demo model: 5 successes."""
    real = await add_model(session, "real-model")
    demo = await add_model(session, "demo-model", provider="demo")
    for latency in range(100, 1001, 100):
        await add_request(session, real, latency_ms=latency, minutes_ago=10)
    for _ in range(2):
        await add_request(session, real, latency_ms=30_000, status="error", minutes_ago=20)
    for _ in range(5):
        await add_request(session, demo, latency_ms=50, minutes_ago=15, token_count_source="estimated")
    # Outside the 1h window; must not be counted.
    await add_request(session, real, latency_ms=99_999, minutes_ago=180)
    return real, demo


async def test_percentiles_use_successful_requests_only(client, recorded_traffic):
    data = (await client.get("/api/analytics", params={"window": "1h", "data_source": "real"})).json()

    summary = data["summary"]
    assert summary["total_requests"] == 12
    assert summary["error_requests"] == 2
    assert summary["error_rate"] == pytest.approx(2 / 12)
    # percentile_cont over 100..1000: linear interpolation between neighbours.
    assert summary["latency"]["p50_ms"] == pytest.approx(550)
    assert summary["latency"]["p95_ms"] == pytest.approx(955)
    assert summary["latency"]["p99_ms"] == pytest.approx(991)
    assert summary["avg_latency_ms"] == pytest.approx(550)
    assert summary["total_tokens"] == 10 * 30
    assert summary["requests_per_second"] == pytest.approx(12 / 3600)
    assert summary["token_throughput_per_second"] == pytest.approx(300 / 3600)
    assert summary["exact_token_share"] == 1.0
    assert data["scope"] == {
        "data_source": "real",
        "demo_requests": 0,
        "real_requests": 12,
        "includes_demo_data": False,
    }


async def test_demo_data_is_reported_when_included(client, recorded_traffic):
    data = (await client.get("/api/analytics", params={"window": "1h", "data_source": "all"})).json()

    assert data["summary"]["total_requests"] == 17
    assert data["scope"]["includes_demo_data"] is True
    assert data["scope"]["demo_requests"] == 5
    # 5 of 15 successful requests used estimated token counts.
    assert data["summary"]["exact_token_share"] == pytest.approx(10 / 15)


async def test_demo_only_view(client, recorded_traffic):
    data = (await client.get("/api/analytics", params={"window": "1h", "data_source": "demo"})).json()

    assert data["summary"]["total_requests"] == 5
    assert data["scope"]["real_requests"] == 0


async def test_default_data_source_is_real_outside_demo_mode(client, recorded_traffic):
    data = (await client.get("/api/analytics", params={"window": "1h"})).json()

    assert data["scope"]["data_source"] == "real"
    assert data["summary"]["total_requests"] == 12


async def test_model_filter_and_comparison(client, recorded_traffic):
    real, demo = recorded_traffic

    filtered = (
        await client.get("/api/analytics", params={"window": "1h", "data_source": "all", "model_id": str(demo.id)})
    ).json()
    assert filtered["summary"]["total_requests"] == 5

    everything = (await client.get("/api/analytics", params={"window": "1h", "data_source": "all"})).json()
    by_name = {row["model_name"]: row for row in everything["models"]}
    assert by_name["real-model"]["stats"]["total_requests"] == 12
    assert by_name["real-model"]["is_demo"] is False
    assert by_name["demo-model"]["is_demo"] is True
    assert everything["models"][0]["model_name"] == "real-model"  # busiest first


async def test_timeseries_covers_window_and_sums_to_total(client, recorded_traffic):
    data = (await client.get("/api/analytics", params={"window": "1h", "data_source": "all"})).json()

    assert data["bucket_seconds"] == 60
    assert 60 <= len(data["timeseries"]) <= 62
    assert sum(point["requests"] for point in data["timeseries"]) == 17
    assert sum(point["errors"] for point in data["timeseries"]) == 2
    empty = [p for p in data["timeseries"] if p["requests"] == 0]
    assert empty and all(p["p95_ms"] is None and p["error_rate"] is None for p in empty)


async def test_empty_window_returns_zeroes(client):
    data = (await client.get("/api/analytics", params={"window": "6h"})).json()

    assert data["summary"]["total_requests"] == 0
    assert data["summary"]["error_rate"] is None
    assert data["summary"]["latency"] == {"p50_ms": None, "p95_ms": None, "p99_ms": None}
    assert data["models"] == []


async def test_invalid_window_is_rejected(client):
    response = await client.get("/api/analytics", params={"window": "2h"})
    assert response.status_code == 422


async def test_overview_combines_kpis_models_and_system_health(client, session, recorded_traffic):
    real, _ = recorded_traffic
    await add_request(session, real, latency_ms=400, minutes_ago=90)  # previous 1h period

    data = (await client.get("/api/overview", params={"window": "1h", "data_source": "real"})).json()

    assert data["summary"]["total_requests"] == 12
    assert data["previous_summary"]["total_requests"] == 1
    assert len(data["timeseries"]) >= 60
    models = {m["name"]: m for m in data["models"]}
    assert models["real-model"]["requests"] == 12
    assert models["real-model"]["p95_ms"] == pytest.approx(955)
    assert models["demo-model"]["requests"] == 0  # excluded by data_source=real
    system = data["system"]
    assert system["database_ok"] is True
    assert 0 <= system["cpu_percent"] <= 100
    assert system["models"]["total"] == 2
    if not system["gpu_available"]:
        assert system["gpu_unavailable_reason"]
