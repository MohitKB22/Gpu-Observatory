"""Prometheus metrics exposed at GET /metrics.

A dedicated registry keeps the output limited to Observatory metrics. Model names are used as
labels; their cardinality is bounded by the number of registered models.
"""

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

REGISTRY = CollectorRegistry()

INFERENCE_REQUESTS = Counter(
    "observatory_inference_requests_total",
    "Inference requests executed through the Observatory.",
    ["model", "provider", "status", "demo"],
    registry=REGISTRY,
)
INFERENCE_LATENCY = Histogram(
    "observatory_inference_latency_seconds",
    "End-to-end inference latency measured by the Observatory backend.",
    ["model", "provider", "demo"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 15, 30, 60, 120),
    registry=REGISTRY,
)
INFERENCE_TOKENS = Counter(
    "observatory_inference_tokens_total",
    "Tokens processed (see the `counted` label for exact vs estimated).",
    ["model", "provider", "kind", "counted", "demo"],
    registry=REGISTRY,
)
MODEL_UP = Gauge(
    "observatory_model_up",
    "1 if the last connection check succeeded, 0 otherwise.",
    ["model", "provider"],
    registry=REGISTRY,
)
HOST_CPU_PERCENT = Gauge("observatory_host_cpu_percent", "Host CPU utilisation.", registry=REGISTRY)
HOST_MEMORY_PERCENT = Gauge("observatory_host_memory_percent", "Host memory utilisation.", registry=REGISTRY)
# Labelled per GPU so the series does not exist at all until a real reading is recorded.
# (An unlabelled gauge would export 0, which would read as "idle GPU" on a machine without one.)
GPU_UTILIZATION_PERCENT = Gauge(
    "observatory_gpu_utilization_percent", "GPU utilisation from NVML or nvidia-smi.", ["gpu"], registry=REGISTRY
)
GPU_MEMORY_USED_BYTES = Gauge(
    "observatory_gpu_memory_used_bytes", "GPU memory in use from NVML or nvidia-smi.", ["gpu"], registry=REGISTRY
)


def record_inference(
    *,
    model: str,
    provider: str,
    status: str,
    is_demo: bool,
    latency_seconds: float,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    token_count_source: str | None,
) -> None:
    demo = "true" if is_demo else "false"
    INFERENCE_REQUESTS.labels(model, provider, status, demo).inc()
    INFERENCE_LATENCY.labels(model, provider, demo).observe(latency_seconds)
    if token_count_source:
        INFERENCE_TOKENS.labels(model, provider, "prompt", token_count_source, demo).inc(prompt_tokens or 0)
        INFERENCE_TOKENS.labels(model, provider, "completion", token_count_source, demo).inc(completion_tokens or 0)
