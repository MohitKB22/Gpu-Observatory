"""Model registry, inference performance, batching and comparison endpoints."""

DEMO = {"source": "demo"}


async def test_model_registration_flow(client, admin_headers):
    created = await client.post(
        "/api/v1/models",
        headers=admin_headers,
        params=DEMO,
        json={
            "name": "test-llm",
            "version": "2.1.0",
            "framework": "vllm",
            "parameter_count_b": 7.0,
            "quantization": "fp8",
            "context_length": 32768,
            "max_batch_size": 64,
        },
    )
    assert created.status_code == 201
    model = created.json()
    assert model["name"] == "test-llm"
    assert model["data_source"] == "demo"

    fetched = await client.get(f"/api/v1/models/{model['id']}", headers=admin_headers, params=DEMO)
    assert fetched.status_code == 200
    assert fetched.json()["quantization"] == "fp8"


async def test_duplicate_model_version_is_rejected(client, admin_headers):
    body = {"name": "dupe-model", "version": "1.0.0"}
    first = await client.post("/api/v1/models", headers=admin_headers, params=DEMO, json=body)
    assert first.status_code == 201
    second = await client.post("/api/v1/models", headers=admin_headers, params=DEMO, json=body)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


async def test_model_validation_rejects_bad_input(client, admin_headers):
    for payload in (
        {"name": ""},
        {"name": "x", "framework": "not-a-framework"},
        {"name": "x", "quantization": "not-a-quant"},
        {"name": "x", "parameter_count_b": -5},
        {"name": "x", "max_batch_size": 0},
    ):
        response = await client.post(
            "/api/v1/models", headers=admin_headers, params=DEMO, json=payload
        )
        assert response.status_code == 422, payload


async def test_model_list_supports_search_and_sort(client, admin_headers, seeded_demo):
    response = await client.get(
        "/api/v1/models",
        headers=admin_headers,
        params={**DEMO, "search": "llama", "sort": "name", "order": "asc"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    assert items and all("llama" in i["name"].lower() for i in items)


async def test_model_update(client, admin_headers, seeded_demo):
    model_id = (await client.get("/api/v1/models", headers=admin_headers, params=DEMO)).json()[
        "items"
    ][0]["id"]
    response = await client.patch(
        f"/api/v1/models/{model_id}",
        headers=admin_headers,
        params=DEMO,
        json={"description": "updated by test", "tags": "demo,updated"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "updated by test"


async def test_deployment_requires_an_existing_model(client, admin_headers):
    response = await client.post(
        "/api/v1/deployments",
        headers=admin_headers,
        params=DEMO,
        json={"model_id": "00000000-0000-0000-0000-000000000000", "name": "orphan"},
    )
    assert response.status_code == 422


async def test_inference_metrics_summary(client, admin_headers, seeded_demo):
    response = await client.get(
        "/api/v1/inference/metrics", headers=admin_headers, params={**DEMO, "range": "1h"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["request_count"] > 0
    latency = body["latency"]
    # Percentiles must be monotonically ordered.
    assert latency["p50"] <= latency["p90"] <= latency["p95"] <= latency["p99"]
    assert latency["min"] <= latency["p50"]
    assert latency["max"] >= latency["p99"]
    assert body["tokens_per_second"] > 0


async def test_latency_distribution_histogram(client, admin_headers, seeded_demo):
    response = await client.get(
        "/api/v1/inference/latency",
        headers=admin_headers,
        params={**DEMO, "range": "1h", "bins": 12},
    )
    assert response.status_code == 200
    buckets = response.json()
    assert buckets
    assert sum(b["count"] for b in buckets) > 0
    assert all(b["lower_ms"] >= 0 for b in buckets)


async def test_request_table_supports_error_filter(client, admin_headers, seeded_demo):
    response = await client.get(
        "/api/v1/inference/requests",
        headers=admin_headers,
        params={**DEMO, "range": "1h", "errors_only": True, "limit": 20},
    )
    assert response.status_code == 200
    assert all(item["is_error"] for item in response.json()["items"])


async def test_batching_analytics_detects_under_batching(client, admin_headers, seeded_demo):
    response = await client.get(
        "/api/v1/batches", headers=admin_headers, params={**DEMO, "range": "1h"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["under_batching_detected"] is True
    assert body["avg_batch_size"] < body["configured_max_batch_size"]
    assert 0 <= body["batch_efficiency"] <= 1


async def test_model_comparison_produces_a_computed_recommendation(
    client, admin_headers, seeded_demo
):
    models = (await client.get("/api/v1/models", headers=admin_headers, params=DEMO)).json()[
        "items"
    ]
    ids = ",".join(m["id"] for m in models[:2])
    response = await client.get(
        "/api/v1/comparisons/models",
        headers=admin_headers,
        params={**DEMO, "model_ids": ids, "range": "1h"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["models"]) == 2
    assert body["deltas"]
    # With only one model carrying traffic, the tool must decline rather than guess.
    assert body["recommendation"] is not None or body["caveats"]


async def test_comparison_requires_two_distinct_models(client, admin_headers, seeded_demo):
    models = (await client.get("/api/v1/models", headers=admin_headers, params=DEMO)).json()[
        "items"
    ]
    response = await client.get(
        "/api/v1/comparisons/models",
        headers=admin_headers,
        params={**DEMO, "model_ids": models[0]["id"]},
    )
    assert response.status_code == 422


async def test_comparison_rejects_unknown_model(client, admin_headers, seeded_demo):
    models = (await client.get("/api/v1/models", headers=admin_headers, params=DEMO)).json()[
        "items"
    ]
    response = await client.get(
        "/api/v1/comparisons/models",
        headers=admin_headers,
        params={**DEMO, "model_ids": f"{models[0]['id']},00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


async def test_recording_inference_requests(client, admin_headers):
    response = await client.post(
        "/api/v1/inference/requests",
        headers=admin_headers,
        json=[
            {
                "total_latency_ms": 120.5,
                "input_tokens": 100,
                "output_tokens": 50,
                "batch_size": 8,
                "data_source": "production",
            },
            {
                "total_latency_ms": 98.2,
                "input_tokens": 90,
                "output_tokens": 40,
                "batch_size": 8,
                "data_source": "production",
            },
        ],
    )
    assert response.status_code == 200
    assert response.json()["records"] == 2


async def test_recording_rejects_empty_and_invalid_batches(client, admin_headers):
    assert (
        await client.post("/api/v1/inference/requests", headers=admin_headers, json=[])
    ).status_code == 422
    assert (
        await client.post(
            "/api/v1/inference/requests",
            headers=admin_headers,
            json=[{"total_latency_ms": -5}],
        )
    ).status_code == 422
