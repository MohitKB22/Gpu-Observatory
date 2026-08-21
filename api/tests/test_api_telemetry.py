"""GPU, system and overview API endpoints."""

DEMO = {"source": "demo"}


async def test_list_gpus_empty_in_production(client, admin_headers):
    response = await client.get(
        "/api/v1/gpus", headers=admin_headers, params={"source": "production"}
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_gpu_availability_is_honest_without_hardware(client, admin_headers):
    response = await client.get(
        "/api/v1/gpus/availability", headers=admin_headers, params={"source": "production"}
    )
    assert response.status_code == 200
    body = response.json()
    if not body["nvml_available"]:
        assert body["reason"], "the API must explain why GPU telemetry is unavailable"
        assert body["gpu_count"] == 0


async def test_demo_gpus_are_listed(client, admin_headers, seeded_demo):
    response = await client.get("/api/v1/gpus", headers=admin_headers, params=DEMO)
    assert response.status_code == 200
    gpus = response.json()
    assert len(gpus) == 4
    assert all(g["data_source"] == "demo" for g in gpus)
    assert all("simulated" in g["name"].lower() for g in gpus)


async def test_gpu_detail_includes_latest_and_processes(client, admin_headers, seeded_demo):
    gpu_id = (await client.get("/api/v1/gpus", headers=admin_headers, params=DEMO)).json()[0]["id"]
    response = await client.get(f"/api/v1/gpus/{gpu_id}", headers=admin_headers, params=DEMO)
    assert response.status_code == 200
    body = response.json()
    assert body["latest"]["utilization_pct"] is not None
    assert body["processes"]
    assert "is_stale" in body["freshness"]


async def test_unknown_gpu_returns_404_envelope(client, admin_headers):
    response = await client.get(
        "/api/v1/gpus/00000000-0000-0000-0000-000000000000", headers=admin_headers, params=DEMO
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_gpu_metrics_are_paginated(client, admin_headers, seeded_demo):
    gpu_id = (await client.get("/api/v1/gpus", headers=admin_headers, params=DEMO)).json()[0]["id"]
    response = await client.get(
        f"/api/v1/gpus/{gpu_id}/metrics",
        headers=admin_headers,
        params={**DEMO, "limit": 5, "range": "1h"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) <= 5
    assert body["meta"]["total"] >= len(body["items"])


async def test_pagination_rejects_oversized_limit(client, admin_headers, seeded_demo):
    gpu_id = (await client.get("/api/v1/gpus", headers=admin_headers, params=DEMO)).json()[0]["id"]
    response = await client.get(
        f"/api/v1/gpus/{gpu_id}/metrics", headers=admin_headers, params={**DEMO, "limit": 99999}
    )
    assert response.status_code == 422


async def test_gpu_timeseries_is_bucketed(client, admin_headers, seeded_demo):
    response = await client.get(
        "/api/v1/gpus/series/timeseries",
        headers=admin_headers,
        params={**DEMO, "range": "1h", "metrics": "utilization_pct,temperature_c"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["bucket_seconds"] > 0
    assert body["series"]
    # A dashboard request must never return an unbounded point count.
    assert all(len(s["points"]) <= 2880 for s in body["series"])


async def test_invalid_time_range_is_rejected(client, admin_headers):
    response = await client.get(
        "/api/v1/gpus/series/timeseries", headers=admin_headers, params={**DEMO, "range": "99y"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_system_metrics_endpoint(client, admin_headers, seeded_demo):
    response = await client.get("/api/v1/system/metrics", headers=admin_headers, params=DEMO)
    assert response.status_code == 200
    body = response.json()
    assert body["latest"]["cpu_utilization_pct"] is not None
    assert isinstance(body["latest"]["per_core_utilization"], list)


async def test_overview_kpis_are_computed(client, admin_headers, seeded_demo):
    response = await client.get(
        "/api/v1/overview", headers=admin_headers, params={**DEMO, "range": "1h"}
    )
    assert response.status_code == 200
    body = response.json()
    keys = {k["key"] for k in body["kpis"]}
    assert {
        "gpu_utilization",
        "vram_usage",
        "cpu_utilization",
        "p95_latency",
        "throughput",
        "tokens_per_second",
        "cost_per_request",
        "error_rate",
    } == keys
    gpu_kpi = next(k for k in body["kpis"] if k["key"] == "gpu_utilization")
    assert gpu_kpi["value"] is not None
    cost_kpi = next(k for k in body["kpis"] if k["key"] == "cost_per_request")
    assert cost_kpi["is_estimate"] is True


async def test_overview_on_empty_production_returns_nulls_not_fabrications(client, admin_headers):
    response = await client.get(
        "/api/v1/overview", headers=admin_headers, params={"source": "production"}
    )
    assert response.status_code == 200
    body = response.json()
    assert all(
        k["value"] is None for k in body["kpis"]
    ), "with no telemetry every KPI must be null rather than an invented number"
    assert body["freshness"]["is_stale"] is True


async def test_telemetry_ingest_accepts_agent_payload(client, admin_headers):
    payload = {
        "host": "gpu-node-7",
        "data_source": "production",
        "gpus": [
            {
                "uuid": "GPU-INGEST-TEST-0001",
                "index": 0,
                "utilization_pct": 77.5,
                "memory_utilization_pct": 61.0,
                "memory_used_mb": 50000.0,
                "memory_total_mb": 81920.0,
                "temperature_c": 68.0,
                "power_w": 402.0,
            }
        ],
        "system": {"cpu_utilization_pct": 44.0, "ram_utilization_pct": 55.0, "core_count": 64},
    }
    response = await client.post("/api/v1/telemetry/ingest", headers=admin_headers, json=payload)
    assert response.status_code == 200
    assert response.json()["gpu_samples"] == 1

    listed = await client.get(
        "/api/v1/gpus", headers=admin_headers, params={"source": "production"}
    )
    assert any(g["uuid"] == "GPU-INGEST-TEST-0001" for g in listed.json())


async def test_demo_and_production_are_isolated_across_the_api(client, admin_headers, seeded_demo):
    demo = (await client.get("/api/v1/gpus", headers=admin_headers, params=DEMO)).json()
    production = (
        await client.get("/api/v1/gpus", headers=admin_headers, params={"source": "production"})
    ).json()
    assert len(demo) == 4
    assert production == []


async def test_invalid_data_source_is_rejected(client, admin_headers):
    response = await client.get(
        "/api/v1/gpus", headers=admin_headers, params={"source": "not-a-source"}
    )
    assert response.status_code == 422
