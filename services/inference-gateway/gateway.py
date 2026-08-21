"""Inference gateway.

Sits in front of an inference backend, forwards requests through the shared
adapters, and records the observed timings to the Observatory. Observability is
applied as middleware so instrumentation cannot be forgotten per-route.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from starlette.responses import Response

sys.path.insert(0, os.environ.get("NVO_API_PATH", "/opt/nvo-api"))

from app.inference.adapters import InferenceRequestSpec, build_adapter  # noqa: E402

API_URL = os.environ.get("NVO_API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("NVO_API_KEY", "")
DATA_SOURCE = os.environ.get("DATA_SOURCE", "production")
DEPLOYMENT_ID = os.environ.get("NVO_DEPLOYMENT_ID") or None
MODEL_ID = os.environ.get("NVO_MODEL_ID") or None
FLUSH_EVERY = int(os.environ.get("FLUSH_EVERY", "20"))

GATEWAY_REQUESTS = Counter(
    "nvo_gateway_requests_total", "Requests handled by the gateway.", ["status"]
)
GATEWAY_LATENCY = Histogram(
    "nvo_gateway_latency_seconds",
    "End-to-end gateway latency.",
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
)
FORWARD_FAILURES = Counter(
    "nvo_gateway_forward_failures_total", "Failures reporting telemetry upstream."
)

_buffer: list[dict[str, Any]] = []
_adapter = build_adapter()


async def _flush(force: bool = False) -> None:
    """Report buffered request records to the Observatory."""
    global _buffer
    if not _buffer or (len(_buffer) < FLUSH_EVERY and not force):
        return
    batch, _buffer = _buffer, []
    if not API_KEY:
        return  # Nothing to report to; metrics remain available at /metrics.
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{API_URL}/api/v1/inference/requests",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json=batch,
            )
            if response.status_code >= 400:
                FORWARD_FAILURES.inc()
    except Exception:
        FORWARD_FAILURES.inc()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    await _flush(force=True)
    await _adapter.close()


app = FastAPI(
    title="NVIDIA AI Performance Observatory — Inference Gateway",
    version="1.0.0",
    lifespan=lifespan,
)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=100_000)
    model: str = Field(default="default", max_length=200)
    max_tokens: int = Field(default=128, ge=1, le=32_000)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)


@app.middleware("http")
async def observe(request: Request, call_next):
    """Attach a trace id and record gateway latency for every route."""
    trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    started = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - started
    if request.url.path == "/v1/generate":
        GATEWAY_LATENCY.observe(duration)
        GATEWAY_REQUESTS.labels(status=str(response.status_code)).inc()
    response.headers["X-Trace-ID"] = trace_id
    return response


@app.get("/health")
async def health() -> dict[str, Any]:
    ok, detail = await _adapter.health()
    return {"status": "ok", "backend": _adapter.name, "backend_healthy": ok, "detail": detail}


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/v1/generate")
async def generate(payload: GenerateRequest, request: Request) -> JSONResponse:
    result = await _adapter.infer(
        InferenceRequestSpec(
            prompt=payload.prompt,
            model=payload.model,
            max_tokens=payload.max_tokens,
            temperature=payload.temperature,
        )
    )

    _buffer.append(
        {
            "deployment_id": DEPLOYMENT_ID,
            "model_id": MODEL_ID,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "total_latency_ms": result.total_latency_ms,
            "queue_latency_ms": result.queue_latency_ms,
            "preprocess_latency_ms": result.preprocess_latency_ms,
            "execution_latency_ms": result.execution_latency_ms,
            "postprocess_latency_ms": result.postprocess_latency_ms,
            "time_to_first_token_ms": result.time_to_first_token_ms,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "batch_size": result.batch_size,
            "status_code": result.status_code,
            "is_error": result.is_error,
            "error_type": result.error_type,
            "trace_id": getattr(request.state, "trace_id", None),
            "data_source": DATA_SOURCE,
        }
    )
    await _flush()

    return JSONResponse(
        status_code=result.status_code,
        content={
            "text": result.text,
            "usage": {
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            },
            "timings_ms": {
                "total": result.total_latency_ms,
                "queue": result.queue_latency_ms,
                "execution": result.execution_latency_ms,
            },
            "backend": result.backend,
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )
