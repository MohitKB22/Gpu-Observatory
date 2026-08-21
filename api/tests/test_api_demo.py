"""Demo Mode API surface and workload generation."""

DEMO = {"source": "demo"}


async def test_demo_state_lists_all_scenarios(client, admin_headers):
    response = await client.get("/api/v1/demo", headers=admin_headers)
    assert response.status_code == 200
    body = response.json()
    assert len(body["available_scenarios"]) == 7
    assert body["scenario"] in body["available_scenarios"]


async def test_demo_scenarios_are_described(client, admin_headers):
    response = await client.get("/api/v1/demo/scenarios", headers=admin_headers)
    assert response.status_code == 200
    scenarios = response.json()
    assert len(scenarios) == 7
    assert all(s["description"] and s["expected_diagnosis"] for s in scenarios)


async def test_workload_profiles_are_listed(client, admin_headers):
    response = await client.get("/api/v1/workloads/profiles", headers=admin_headers)
    assert response.status_code == 200
    keys = {p["key"] for p in response.json()}
    assert keys == {
        "low_concurrency",
        "high_concurrency",
        "small_batch",
        "large_batch",
        "latency_spike",
        "memory_pressure",
    }


async def test_workload_creation_returns_accepted(client, admin_headers):
    response = await client.post(
        "/api/v1/workloads",
        headers=admin_headers,
        json={
            "name": "short-smoke",
            "profile": "low_concurrency",
            "duration_seconds": 1,
            "target_rps": 2,
        },
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] in ("pending", "running")
    assert body["data_source"] == "demo"


async def test_workload_validation(client, admin_headers):
    response = await client.post(
        "/api/v1/workloads",
        headers=admin_headers,
        json={"name": "bad", "profile": "not-a-profile"},
    )
    assert response.status_code == 422


async def test_unknown_workload_is_404(client, admin_headers):
    response = await client.get(
        "/api/v1/workloads/00000000-0000-0000-0000-000000000000", headers=admin_headers
    )
    assert response.status_code == 404


async def test_demo_backfill_endpoint(client, admin_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DEMO_MODE", True)
    response = await client.post(
        "/api/v1/demo/backfill",
        headers=admin_headers,
        params={"minutes": 10, "scenario": "healthy", "reset": True},
    )
    assert response.status_code == 200
    assert response.json()["gpu_samples"] > 0


async def test_demo_backfill_rejects_unknown_scenario(client, admin_headers, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "DEMO_MODE", True)
    response = await client.post(
        "/api/v1/demo/backfill", headers=admin_headers, params={"scenario": "nope"}
    )
    assert response.status_code == 422


async def test_clearing_demo_data_leaves_production_untouched(
    client, admin_headers, session, seeded_demo
):
    await client.post(
        "/api/v1/telemetry/ingest",
        headers=admin_headers,
        json={
            "host": "real-node",
            "data_source": "production",
            "gpus": [{"uuid": "GPU-PROD-KEEP", "index": 0, "utilization_pct": 50.0}],
        },
    )
    cleared = await client.delete("/api/v1/demo/data", headers=admin_headers)
    assert cleared.status_code == 200

    demo_gpus = (await client.get("/api/v1/gpus", headers=admin_headers, params=DEMO)).json()
    production_gpus = (
        await client.get("/api/v1/gpus", headers=admin_headers, params={"source": "production"})
    ).json()
    assert demo_gpus == []
    assert any(g["uuid"] == "GPU-PROD-KEEP" for g in production_gpus)
