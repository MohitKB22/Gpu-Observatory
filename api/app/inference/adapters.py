"""Inference backend adapters.

A uniform interface over vLLM, NVIDIA Triton and OpenAI-compatible servers,
plus a local adapter used for development and testing. Each adapter reports
the timing breakdown the observability layer needs.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import UpstreamError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class InferenceRequestSpec:
    prompt: str
    model: str
    max_tokens: int = 128
    temperature: float = 0.0
    stream: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class InferenceResult:
    text: str
    input_tokens: int
    output_tokens: int
    total_latency_ms: float
    queue_latency_ms: float | None = None
    preprocess_latency_ms: float | None = None
    execution_latency_ms: float | None = None
    postprocess_latency_ms: float | None = None
    time_to_first_token_ms: float | None = None
    batch_size: int | None = None
    status_code: int = 200
    is_error: bool = False
    error_type: str | None = None
    backend: str = "local"


class InferenceAdapter(ABC):
    name: str = "abstract"

    @abstractmethod
    async def infer(self, spec: InferenceRequestSpec) -> InferenceResult: ...

    @abstractmethod
    async def health(self) -> tuple[bool, str]: ...

    async def close(self) -> None:  # pragma: no cover - default no-op
        return None


class LocalEchoAdapter(InferenceAdapter):
    """Deterministic local adapter.

    Provides a working inference path with realistic timing when no external
    serving backend is reachable, so the gateway and its instrumentation can be
    exercised end to end. It performs no model computation and says so.
    """

    name = "local"

    def __init__(self, base_latency_ms: float = 45.0, seed: int | None = None) -> None:
        self._base = base_latency_ms
        self._rng = random.Random(seed)

    async def infer(self, spec: InferenceRequestSpec) -> InferenceResult:
        started = time.perf_counter()
        input_tokens = max(1, len(spec.prompt.split()))
        output_tokens = min(spec.max_tokens, max(1, input_tokens // 2 + 8))

        queue = self._rng.uniform(0.2, 2.5)
        preprocess = self._rng.uniform(0.4, 1.8)
        execution = self._base + output_tokens * self._rng.uniform(0.7, 1.4)
        postprocess = self._rng.uniform(0.2, 1.0)

        # Simulate the wall-clock cost so concurrency behaves realistically.
        await asyncio.sleep((queue + preprocess + execution + postprocess) / 1000.0)
        total = (time.perf_counter() - started) * 1000.0

        return InferenceResult(
            text=f"[local-adapter] processed {input_tokens} input tokens "
            f"(no model computation performed)",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_latency_ms=round(total, 3),
            queue_latency_ms=round(queue, 3),
            preprocess_latency_ms=round(preprocess, 3),
            execution_latency_ms=round(execution, 3),
            postprocess_latency_ms=round(postprocess, 3),
            time_to_first_token_ms=round(queue + preprocess + execution * 0.2, 3),
            batch_size=1,
            backend=self.name,
        )

    async def health(self) -> tuple[bool, str]:
        return True, "local adapter ready (no external backend)"


class OpenAICompatibleAdapter(InferenceAdapter):
    """Any server exposing /v1/chat/completions -- vLLM, TGI, LM Studio, OpenAI."""

    name = "openai"

    def __init__(self, base_url: str, api_key: str = "", timeout: float | None = None) -> None:
        self._base_url = (base_url or "http://localhost:8000/v1").rstrip("/")
        self._api_key = api_key
        self._timeout = timeout or settings.INFERENCE_TIMEOUT_SECONDS

    async def infer(self, spec: InferenceRequestSpec) -> InferenceResult:
        started = time.perf_counter()
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        payload = {
            "model": spec.model,
            "messages": [{"role": "user", "content": spec.prompt}],
            "max_tokens": spec.max_tokens,
            "temperature": spec.temperature,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions", headers=headers, json=payload
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            return self._error_result(started, exc.response.status_code, "upstream_http_error")
        except Exception as exc:
            logger.warning("inference_upstream_failed", error=str(exc)[:200])
            return self._error_result(started, 502, "upstream_unreachable")

        total = (time.perf_counter() - started) * 1000.0
        usage = data.get("usage", {}) or {}
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content", "") or ""
        return InferenceResult(
            text=text,
            input_tokens=int(usage.get("prompt_tokens", len(spec.prompt.split()))),
            output_tokens=int(usage.get("completion_tokens", len(text.split()))),
            total_latency_ms=round(total, 3),
            execution_latency_ms=round(total, 3),
            backend=self.name,
        )

    def _error_result(self, started: float, status: int, error_type: str) -> InferenceResult:
        return InferenceResult(
            text="",
            input_tokens=0,
            output_tokens=0,
            total_latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
            status_code=status,
            is_error=True,
            error_type=error_type,
            backend=self.name,
        )

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/models")
                return response.status_code < 500, f"HTTP {response.status_code}"
        except Exception as exc:
            return False, str(exc)[:160]


class VLLMAdapter(OpenAICompatibleAdapter):
    """vLLM exposes an OpenAI-compatible API plus its own metrics endpoint."""

    name = "vllm"

    def __init__(self, base_url: str, api_key: str = "", timeout: float | None = None) -> None:
        super().__init__(base_url or "http://localhost:8000/v1", api_key, timeout)

    async def scrape_metrics(self) -> dict[str, float]:
        """Read vLLM's /metrics for scheduler state the OpenAI API does not expose."""
        root = self._base_url.removesuffix("/v1")
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{root}/metrics")
                response.raise_for_status()
        except Exception:
            return {}

        wanted = {
            "vllm:num_requests_running": "requests_running",
            "vllm:num_requests_waiting": "requests_waiting",
            "vllm:gpu_cache_usage_perc": "gpu_cache_usage",
        }
        out: dict[str, float] = {}
        for line in response.text.splitlines():
            if line.startswith("#"):
                continue
            for metric, key in wanted.items():
                if line.startswith(metric):
                    with contextlib.suppress(ValueError):
                        out[key] = float(line.rsplit(" ", 1)[-1])
        return out


class TritonAdapter(InferenceAdapter):
    """NVIDIA Triton Inference Server via its KServe v2 HTTP API."""

    name = "triton"

    def __init__(self, base_url: str, timeout: float | None = None) -> None:
        self._base_url = (base_url or "http://localhost:8000").rstrip("/")
        self._timeout = timeout or settings.INFERENCE_TIMEOUT_SECONDS

    async def infer(self, spec: InferenceRequestSpec) -> InferenceResult:
        started = time.perf_counter()
        payload = {
            "inputs": [
                {
                    "name": "text_input",
                    "shape": [1, 1],
                    "datatype": "BYTES",
                    "data": [spec.prompt],
                }
            ],
            "parameters": {"max_tokens": spec.max_tokens, "temperature": spec.temperature},
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/v2/models/{spec.model}/infer", json=payload
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            return InferenceResult(
                text="",
                input_tokens=0,
                output_tokens=0,
                total_latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
                status_code=exc.response.status_code,
                is_error=True,
                error_type="triton_http_error",
                backend=self.name,
            )
        except Exception as exc:
            logger.warning("triton_request_failed", error=str(exc)[:200])
            return InferenceResult(
                text="",
                input_tokens=0,
                output_tokens=0,
                total_latency_ms=round((time.perf_counter() - started) * 1000.0, 3),
                status_code=502,
                is_error=True,
                error_type="triton_unreachable",
                backend=self.name,
            )

        total = (time.perf_counter() - started) * 1000.0
        outputs = data.get("outputs") or [{}]
        raw = outputs[0].get("data") or [""]
        text = raw[0] if isinstance(raw, list) and raw else ""
        return InferenceResult(
            text=str(text),
            input_tokens=len(spec.prompt.split()),
            output_tokens=len(str(text).split()),
            total_latency_ms=round(total, 3),
            execution_latency_ms=round(total, 3),
            backend=self.name,
        )

    async def health(self) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self._base_url}/v2/health/ready")
                return response.status_code == 200, f"HTTP {response.status_code}"
        except Exception as exc:
            return False, str(exc)[:160]


def build_adapter(backend: str | None = None, base_url: str | None = None) -> InferenceAdapter:
    """Construct the configured adapter, falling back to the local adapter."""
    backend = (backend or settings.INFERENCE_BACKEND).lower()
    url = base_url or settings.INFERENCE_BASE_URL

    if backend == "vllm":
        return VLLMAdapter(url)
    if backend == "triton":
        return TritonAdapter(url or "http://localhost:8000")
    if backend == "openai":
        if not url and not settings.LLM_API_KEY:
            logger.warning("inference_backend_unconfigured", backend=backend)
            return LocalEchoAdapter()
        return OpenAICompatibleAdapter(url or "https://api.openai.com/v1", settings.LLM_API_KEY)
    return LocalEchoAdapter()


def raise_if_unavailable(ok: bool, detail: str) -> None:
    if not ok:
        raise UpstreamError("The inference backend is unavailable.", details={"detail": detail})
