"""Prometheus metrics for the observability platform itself.

Section 29 of the specification requires the platform to expose its own
health: API latency/errors, dependency health, telemetry ingestion rate and
failures, agent latency/errors, and live WebSocket connections.
"""

from __future__ import annotations

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    multiprocess,
)
from prometheus_client.core import CollectorRegistry as _Registry

REGISTRY: _Registry = CollectorRegistry(auto_describe=True)

# ------------------------------------------------------------------ HTTP ---
HTTP_REQUESTS = Counter(
    "nvo_http_requests_total",
    "Total HTTP requests handled by the API.",
    ["method", "path", "status"],
    registry=REGISTRY,
)
HTTP_ERRORS = Counter(
    "nvo_http_errors_total",
    "HTTP requests that resulted in a server error.",
    ["method", "path"],
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "nvo_http_request_duration_seconds",
    "API request latency in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)
HTTP_IN_PROGRESS = Gauge(
    "nvo_http_requests_in_progress",
    "HTTP requests currently being processed.",
    registry=REGISTRY,
)
RATE_LIMIT_REJECTIONS = Counter(
    "nvo_rate_limit_rejections_total",
    "Requests rejected by the rate limiter.",
    registry=REGISTRY,
)

# ---------------------------------------------------------- dependencies ---
DEPENDENCY_UP = Gauge(
    "nvo_dependency_up",
    "Dependency reachability (1 = up, 0 = down).",
    ["dependency"],
    registry=REGISTRY,
)

# ------------------------------------------------------------- telemetry ---
TELEMETRY_SAMPLES = Counter(
    "nvo_telemetry_samples_total",
    "Telemetry samples successfully ingested.",
    ["kind", "data_source"],
    registry=REGISTRY,
)
TELEMETRY_FAILURES = Counter(
    "nvo_telemetry_failures_total",
    "Telemetry collection or persistence failures.",
    ["kind", "reason"],
    registry=REGISTRY,
)
TELEMETRY_COLLECT_LATENCY = Histogram(
    "nvo_telemetry_collect_duration_seconds",
    "Time spent collecting one telemetry sweep.",
    ["kind"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
    registry=REGISTRY,
)
TELEMETRY_LAST_SUCCESS = Gauge(
    "nvo_telemetry_last_success_timestamp",
    "Unix timestamp of the last successful telemetry sweep.",
    ["kind"],
    registry=REGISTRY,
)

# ------------------------------------------------- observed GPU telemetry ---
GPU_UTILIZATION = Gauge(
    "nvo_gpu_utilization_percent",
    "Observed GPU utilisation percentage.",
    ["gpu_uuid", "gpu_index", "gpu_name", "data_source"],
    registry=REGISTRY,
)
GPU_MEMORY_USED = Gauge(
    "nvo_gpu_memory_used_megabytes",
    "Observed GPU memory in use.",
    ["gpu_uuid", "gpu_index", "data_source"],
    registry=REGISTRY,
)
GPU_TEMPERATURE = Gauge(
    "nvo_gpu_temperature_celsius",
    "Observed GPU temperature.",
    ["gpu_uuid", "gpu_index", "data_source"],
    registry=REGISTRY,
)
GPU_POWER = Gauge(
    "nvo_gpu_power_watts",
    "Observed GPU power draw.",
    ["gpu_uuid", "gpu_index", "data_source"],
    registry=REGISTRY,
)

# ------------------------------------------------------------- inference ---
INFERENCE_REQUESTS = Counter(
    "nvo_inference_requests_total",
    "Inference requests observed by the gateway.",
    ["deployment", "status", "data_source"],
    registry=REGISTRY,
)
INFERENCE_LATENCY = Histogram(
    "nvo_inference_latency_seconds",
    "End-to-end inference latency.",
    ["deployment", "data_source"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)
INFERENCE_TOKENS = Counter(
    "nvo_inference_tokens_total",
    "Tokens processed, split by direction.",
    ["deployment", "direction", "data_source"],
    registry=REGISTRY,
)

# ----------------------------------------------------------------- agent ---
AGENT_REQUESTS = Counter(
    "nvo_agent_requests_total",
    "AI agent invocations.",
    ["engine", "outcome"],
    registry=REGISTRY,
)
AGENT_LATENCY = Histogram(
    "nvo_agent_duration_seconds",
    "AI agent end-to-end duration.",
    ["engine"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)
AGENT_TOOL_CALLS = Counter(
    "nvo_agent_tool_calls_total",
    "Tool invocations made by the AI agent.",
    ["tool", "outcome"],
    registry=REGISTRY,
)
AGENT_ERRORS = Counter(
    "nvo_agent_errors_total",
    "AI agent failures.",
    ["reason"],
    registry=REGISTRY,
)

# ------------------------------------------------------------- websocket ---
WS_CONNECTIONS = Gauge(
    "nvo_websocket_connections",
    "Currently open WebSocket connections.",
    registry=REGISTRY,
)
WS_MESSAGES = Counter(
    "nvo_websocket_messages_total",
    "Messages pushed to WebSocket clients.",
    ["channel"],
    registry=REGISTRY,
)

# ------------------------------------------------- analytics / diagnostics ---
ANOMALIES_DETECTED = Counter(
    "nvo_anomalies_detected_total",
    "Anomalies detected.",
    ["metric_kind", "severity"],
    registry=REGISTRY,
)
ALERTS_FIRED = Counter(
    "nvo_alerts_fired_total",
    "Alerts fired.",
    ["condition", "severity"],
    registry=REGISTRY,
)
ALERTS_ACTIVE = Gauge(
    "nvo_alerts_active",
    "Alerts currently in the active state.",
    ["severity"],
    registry=REGISTRY,
)
DIAGNOSES_GENERATED = Counter(
    "nvo_diagnoses_generated_total",
    "Diagnoses produced by the diagnostics engine.",
    ["kind", "engine"],
    registry=REGISTRY,
)

# ------------------------------------------------------------------ info ---
BUILD_INFO = Gauge(
    "nvo_build_info",
    "Build and runtime information (value is always 1).",
    ["version", "environment", "demo_mode"],
    registry=REGISTRY,
)
RETENTION_ROWS_DELETED = Counter(
    "nvo_retention_rows_deleted_total",
    "Rows removed by the retention sweeper.",
    ["table"],
    registry=REGISTRY,
)


def render_metrics() -> bytes:
    """Render the registry in Prometheus text exposition format."""
    return generate_latest(REGISTRY)


__all__ = [
    "AGENT_ERRORS",
    "AGENT_LATENCY",
    "AGENT_REQUESTS",
    "AGENT_TOOL_CALLS",
    "ALERTS_ACTIVE",
    "ALERTS_FIRED",
    "ANOMALIES_DETECTED",
    "BUILD_INFO",
    "DEPENDENCY_UP",
    "DIAGNOSES_GENERATED",
    "GPU_MEMORY_USED",
    "GPU_POWER",
    "GPU_TEMPERATURE",
    "GPU_UTILIZATION",
    "HTTP_ERRORS",
    "HTTP_IN_PROGRESS",
    "HTTP_LATENCY",
    "HTTP_REQUESTS",
    "INFERENCE_LATENCY",
    "INFERENCE_REQUESTS",
    "INFERENCE_TOKENS",
    "RATE_LIMIT_REJECTIONS",
    "REGISTRY",
    "RETENTION_ROWS_DELETED",
    "TELEMETRY_COLLECT_LATENCY",
    "TELEMETRY_FAILURES",
    "TELEMETRY_LAST_SUCCESS",
    "TELEMETRY_SAMPLES",
    "WS_CONNECTIONS",
    "WS_MESSAGES",
    "multiprocess",
    "render_metrics",
]
