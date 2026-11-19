import json
import uuid

import httpx
import pytest
from sqlalchemy import func, select

from app.models import InferenceRequest
from app.providers.demo import DEMO_RESPONSE_LABEL
from tests.conftest import register_model

OPENAI_BASE = "https://llm.example.test/v1"
COMPLETIONS_URL = OPENAI_BASE + "/chat/completions"
HF_URL = "https://hf-endpoint.example.test"


def chat_completion(content: str, usage: dict | None = None) -> httpx.Response:
    body: dict = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    if usage is not None:
        body["usage"] = usage
    return httpx.Response(200, json=body)


async def openai_model(client, **overrides) -> dict:
    return await register_model(
        client,
        **{
            "name": "remote",
            "provider": "openai_compatible",
            "model_identifier": "gpt-test",
            "endpoint_url": OPENAI_BASE,
            "api_key": "sk-live",
        }
        | overrides,
    )


async def test_demo_inference_is_recorded_and_labelled(client, session):
    model = await register_model(client, name="demo-a")

    response = await client.post(
        "/api/inference",
        json={"model_id": model["id"], "prompt": "Explain P99 latency", "max_tokens": 64, "source": "playground"},
    )

    result = response.json()
    assert response.status_code == 200
    assert result["status"] == "success"
    assert result["is_demo"] is True
    assert result["source"] == "playground"
    assert result["response_text"].startswith(DEMO_RESPONSE_LABEL)
    metrics = result["metrics"]
    assert metrics["token_count_source"] == "estimated"
    assert 0 < metrics["completion_tokens"] <= 64
    assert metrics["latency_ms"] >= 0

    stored = await session.get(InferenceRequest, uuid.UUID(result["id"]))
    assert stored.metrics.total_tokens == metrics["prompt_tokens"] + metrics["completion_tokens"]


async def test_openai_inference_records_exact_usage_and_sends_expected_payload(client, upstream):
    upstream.on("POST", COMPLETIONS_URL, chat_completion("Hello!", {"prompt_tokens": 12, "completion_tokens": 3}))
    model = await openai_model(client)

    result = (
        await client.post(
            "/api/inference",
            json={
                "model_id": model["id"],
                "prompt": "Say hello",
                "system_prompt": "Be brief",
                "temperature": 0.2,
                "max_tokens": 50,
            },
        )
    ).json()

    assert result["status"] == "success"
    assert result["is_demo"] is False
    assert result["response_text"] == "Hello!"
    assert result["upstream_status_code"] == 200
    assert result["metrics"]["prompt_tokens"] == 12
    assert result["metrics"]["completion_tokens"] == 3
    assert result["metrics"]["token_count_source"] == "exact"

    sent = upstream.requests[-1]
    assert sent.headers["Authorization"] == "Bearer sk-live"
    payload = json.loads(sent.content)
    assert payload["model"] == "gpt-test"
    assert payload["messages"] == [
        {"role": "system", "content": "Be brief"},
        {"role": "user", "content": "Say hello"},
    ]
    assert payload["temperature"] == 0.2 and payload["max_tokens"] == 50 and payload["stream"] is False


async def test_missing_usage_falls_back_to_estimate(client, upstream):
    upstream.on("POST", COMPLETIONS_URL, chat_completion("Some answer text"))
    model = await openai_model(client)

    result = (await client.post("/api/inference", json={"model_id": model["id"], "prompt": "q"})).json()

    assert result["metrics"]["token_count_source"] == "estimated"
    assert result["metrics"]["completion_tokens"] == 4  # 16 chars / 4


async def test_upstream_http_error_is_recorded(client, upstream):
    upstream.on("POST", COMPLETIONS_URL, httpx.Response(503, text="model overloaded"))
    model = await openai_model(client)

    result = (await client.post("/api/inference", json={"model_id": model["id"], "prompt": "q"})).json()

    assert result["status"] == "error"
    assert result["error_kind"] == "http"
    assert result["upstream_status_code"] == 503
    assert "model overloaded" in result["error_message"]
    assert result["response_text"] is None
    assert result["metrics"]["latency_ms"] >= 0
    assert result["metrics"]["total_tokens"] is None
    assert result["metrics"]["token_count_source"] is None


async def test_upstream_timeout_is_recorded(client, upstream):
    def slow(request):
        raise httpx.ReadTimeout("timed out", request=request)

    upstream.on("POST", COMPLETIONS_URL, slow)
    model = await openai_model(client, timeout_seconds=5)

    result = (await client.post("/api/inference", json={"model_id": model["id"], "prompt": "q"})).json()

    assert result["status"] == "error"
    assert result["error_kind"] == "timeout"
    assert result["error_message"] == "No response from the endpoint within 5s"


async def test_malformed_upstream_response_is_recorded(client, upstream):
    upstream.on("POST", COMPLETIONS_URL, httpx.Response(200, json={"unexpected": True}))
    model = await openai_model(client)

    result = (await client.post("/api/inference", json={"model_id": model["id"], "prompt": "q"})).json()

    assert result["status"] == "error"
    assert result["error_kind"] == "invalid_response"


async def test_disabled_model_is_rejected_without_recording(client, session):
    model = await register_model(client, name="off", is_enabled=False)

    response = await client.post("/api/inference", json={"model_id": model["id"], "prompt": "q"})

    assert response.status_code == 409
    assert await session.scalar(select(func.count()).select_from(InferenceRequest)) == 0


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"temperature": 2.5}, "temperature"),
        ({"max_tokens": 0}, "max_tokens"),
        ({"max_tokens": 9000}, "max_tokens"),
        ({"prompt": "   "}, "prompt"),
        ({"prompt": "x" * 32_001}, "prompt"),
        ({"source": "demo_seed"}, "source"),
    ],
)
async def test_invalid_inference_input(client, overrides, field):
    model = await register_model(client, name="m")
    response = await client.post("/api/inference", json={"model_id": model["id"], "prompt": "ok"} | overrides)

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == field


async def test_unknown_model_returns_404(client):
    response = await client.post("/api/inference", json={"model_id": str(uuid.uuid4()), "prompt": "q"})
    assert response.status_code == 404


async def test_huggingface_greedy_request(client, upstream):
    upstream.on("POST", HF_URL, httpx.Response(200, json=[{"generated_text": "Paris"}]))
    model = await register_model(
        client, name="hf", provider="huggingface", model_identifier="mistral", endpoint_url=HF_URL
    )

    result = (
        await client.post(
            "/api/inference", json={"model_id": model["id"], "prompt": "Capital of France?", "temperature": 0}
        )
    ).json()

    assert result["status"] == "success"
    assert result["response_text"] == "Paris"
    assert result["metrics"]["token_count_source"] == "estimated"
    parameters = json.loads(upstream.requests[-1].content)["parameters"]
    assert parameters["do_sample"] is False and "temperature" not in parameters
    assert parameters["return_full_text"] is False


async def test_vllm_uses_openai_chat_api(client, upstream):
    upstream.on(
        "POST",
        "http://gpu-box:8000/v1/chat/completions",
        chat_completion("ok", {"prompt_tokens": 5, "completion_tokens": 1}),
    )
    model = await register_model(
        client, name="vllm", provider="vllm", model_identifier="llama", endpoint_url="http://gpu-box:8000/v1"
    )

    result = (await client.post("/api/inference", json={"model_id": model["id"], "prompt": "q"})).json()

    assert result["status"] == "success"
    assert result["provider"] == "vllm"
    assert result["metrics"]["token_count_source"] == "exact"
