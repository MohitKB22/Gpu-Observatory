import httpx

from tests.conftest import register_model

VLLM_METRICS = """\
# HELP vllm:num_requests_running Number of requests currently running on GPU.
# TYPE vllm:num_requests_running gauge
vllm:num_requests_running{model_name="llama"} 3.0
# HELP vllm:num_requests_waiting Number of requests waiting to be processed.
# TYPE vllm:num_requests_waiting gauge
vllm:num_requests_waiting{model_name="llama"} 7.0
# HELP vllm:kv_cache_usage_perc KV-cache usage. 1 means 100 percent usage.
# TYPE vllm:kv_cache_usage_perc gauge
vllm:kv_cache_usage_perc{model_name="llama"} 0.42
"""


async def test_health_and_system_info(client):
    assert (await client.get("/api/health")).json() == {"status": "ok", "database": "ok"}

    info = (await client.get("/api/system/info")).json()
    assert info["demo_mode"] is False
    assert info["default_data_source"] == "real"
    assert info["environment"] == "test"
    assert info["public_demo"] is False
    assert (info["max_prompt_chars"], info["max_tokens"]) == (32_000, 8192)


async def test_infrastructure_snapshot_reports_real_host_values(client):
    data = (await client.get("/api/infrastructure")).json()

    host = data["host"]
    assert host["cpu_count"] >= 1
    assert 0 <= host["cpu_percent"] <= 100
    assert 0 < host["memory_used_bytes"] <= host["memory_total_bytes"]
    assert data["worker"]["pid"] > 0
    assert data["worker"]["configured_workers"] == 1
    assert data["database"]["ok"] is True
    assert data["database"]["server_version"]


async def test_gpu_section_never_invents_values(client):
    gpu = (await client.get("/api/infrastructure")).json()["gpu"]

    if gpu["available"]:
        assert gpu["devices"] and gpu["source"] in ("nvml", "nvidia-smi")
    else:
        assert gpu["devices"] == []
        assert gpu["unavailable_reason"]


async def test_vllm_server_metrics_are_scraped(client, upstream):
    upstream.on("GET", "http://gpu-box:8000/metrics", httpx.Response(200, text=VLLM_METRICS))
    await register_model(
        client, name="llama", provider="vllm", model_identifier="llama", endpoint_url="http://gpu-box:8000/v1"
    )

    servers = (await client.get("/api/infrastructure")).json()["inference_servers"]

    assert servers == [
        {
            "model_id": servers[0]["model_id"],
            "model_name": "llama",
            "reachable": True,
            "requests_running": 3.0,
            "requests_waiting": 7.0,
            "kv_cache_usage_percent": 42.0,
            "error": None,
        }
    ]


async def test_unreachable_vllm_server_is_reported(client):
    await register_model(
        client, name="llama", provider="vllm", model_identifier="llama", endpoint_url="http://gpu-box:8000/v1"
    )

    server = (await client.get("/api/infrastructure")).json()["inference_servers"][0]

    assert server["reachable"] is False
    assert server["requests_running"] is None
    assert "404" in server["error"]


async def test_usage_history(client):
    await client.get("/api/infrastructure")  # guarantees at least one sample
    history = (await client.get("/api/infrastructure/history")).json()

    assert history["samples"]
    assert {"cpu_percent", "memory_percent", "gpu_utilization_percent"} <= set(history["samples"][0])


async def test_prometheus_metrics_include_inference_counters(client):
    model = await register_model(client, name="prom-demo")
    await client.post("/api/inference", json={"model_id": model["id"], "prompt": "hi"})

    response = await client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'observatory_inference_requests_total{demo="true",model="prom-demo"' in response.text
    assert "observatory_host_cpu_percent" in response.text


async def test_prometheus_exports_no_gpu_series_without_a_gpu(client, app):
    response = await client.get("/metrics")

    if not app.state.sampler.latest_gpu_report.available:
        assert "observatory_gpu_utilization_percent{" not in response.text
        assert "observatory_gpu_memory_used_bytes{" not in response.text


async def test_request_id_header_is_echoed_or_generated(client):
    echoed = await client.get("/api/health", headers={"X-Request-ID": "trace-123"})
    generated = await client.get("/api/health", headers={"X-Request-ID": "bad id\nwith newline"})

    assert echoed.headers["X-Request-ID"] == "trace-123"
    assert generated.headers["X-Request-ID"] != "bad id\nwith newline"
    assert len(generated.headers["X-Request-ID"]) == 32
