"""Unit tests for parsing, estimation, encryption and configuration helpers."""

import httpx
import pytest

from app.config import Settings
from app.models.enums import ProviderKind
from app.monitoring import gpu_metrics
from app.monitoring.gpu_metrics import GpuMonitor, parse_nvidia_smi_output
from app.monitoring.vllm_metrics import parse_vllm_metrics
from app.providers.base import EndpointConfig, ProviderError
from app.providers.demo import DEMO_RESPONSE_LABEL, compose_demo_response
from app.providers.huggingface import HuggingFaceProvider
from app.providers.vllm import server_root_url
from app.security import SecretBox, SecretDecryptionError
from app.utils.tokens import estimate_tokens


@pytest.mark.parametrize(("text", "expected"), [(None, 0), ("", 0), ("a", 1), ("abcd", 1), ("abcde", 2)])
def test_estimate_tokens(text, expected):
    assert estimate_tokens(text) == expected


@pytest.mark.parametrize("max_tokens", [1, 5, 40, 2000])
def test_demo_response_is_labelled_and_respects_max_tokens(max_tokens):
    text = compose_demo_response("What is P95 latency?", max_tokens)

    assert estimate_tokens(text) <= max_tokens
    if max_tokens >= 40:
        assert text.startswith(DEMO_RESPONSE_LABEL)


def test_demo_response_is_stable_for_the_same_prompt():
    assert compose_demo_response("same prompt", 500) == compose_demo_response("same prompt", 500)


def test_parse_nvidia_smi_output_handles_unsupported_fields():
    output = (
        "0, NVIDIA A100-SXM4-80GB, 87, 40960, 81920, 61, 312.5, 550.54\n"
        "1, NVIDIA T4, 0, 0, 15360, [N/A], [Not Supported], 550.54\n"
    )

    report = parse_nvidia_smi_output(output)

    assert report.available and report.source == "nvidia-smi" and report.driver_version == "550.54"
    a100, t4 = report.devices
    assert a100.utilization_percent == 87.0
    assert a100.memory_used_bytes == 40960 * 1024 * 1024
    assert a100.power_watts == 312.5
    assert t4.temperature_celsius is None and t4.power_watts is None


def test_gpu_monitor_reports_unavailable_without_driver(monkeypatch):
    monkeypatch.setattr(gpu_metrics, "_load_nvml", lambda: None)

    report = GpuMonitor(nvidia_smi_path="definitely-not-installed-smi").read()

    assert report.available is False
    assert report.devices == []
    assert "nvidia-smi is not installed" in report.unavailable_reason


def test_parse_vllm_metrics_supports_old_metric_names():
    text = (
        "# TYPE vllm:num_requests_running gauge\n"
        'vllm:num_requests_running{model_name="a"} 2\n'
        "# TYPE vllm:gpu_cache_usage_perc gauge\n"
        'vllm:gpu_cache_usage_perc{model_name="a"} 0.25\n'
    )

    metrics = parse_vllm_metrics(text)

    assert metrics.reachable and metrics.requests_running == 2
    assert metrics.requests_waiting is None
    assert metrics.kv_cache_usage_percent == 25.0


@pytest.mark.parametrize(
    ("url", "root"),
    [("http://h:8000/v1", "http://h:8000"), ("http://h:8000/v1/", "http://h:8000"), ("http://h:8000", "http://h:8000")],
)
def test_vllm_server_root_url(url, root):
    assert server_root_url(url) == root


async def test_huggingface_health_falls_back_when_health_route_missing():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/health"):
            return httpx.Response(404)
        return httpx.Response(200, json={"loaded": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        endpoint = EndpointConfig(ProviderKind.HUGGINGFACE, "m", "https://api.test/models/m", None, 30)
        await HuggingFaceProvider(client).check_health(endpoint)

    assert calls == ["https://api.test/models/m/health", "https://api.test/models/m"]


async def test_huggingface_health_does_not_hide_auth_errors():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as client:
        endpoint = EndpointConfig(ProviderKind.HUGGINGFACE, "m", "https://api.test", "bad", 30)
        with pytest.raises(ProviderError) as error:
            await HuggingFaceProvider(client).check_health(endpoint)

    assert error.value.kind == "auth"


def test_secret_box_round_trip_and_wrong_key():
    token = SecretBox("key-one").encrypt("sk-secret")

    assert SecretBox("key-one").decrypt(token) == "sk-secret"
    with pytest.raises(SecretDecryptionError):
        SecretBox("key-two").decrypt(token)


def test_settings_normalise_database_url():
    settings = Settings(_env_file=None, database_url="postgres://u:p@db:5432/obs")
    assert settings.database_url == "postgresql+psycopg://u:p@db:5432/obs"


@pytest.mark.parametrize("value", ["", "   "])
def test_settings_reject_an_empty_database_url(value):
    with pytest.raises(ValueError, match="DATABASE_URL is empty"):
        Settings(_env_file=None, database_url=value)


def test_production_requires_a_real_secret_key():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(_env_file=None, app_env="production")
    Settings(_env_file=None, app_env="production", secret_key="x" * 32)


def test_cors_origins_are_split():
    settings = Settings(_env_file=None, cors_origins="http://a.test, http://b.test ,")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]
