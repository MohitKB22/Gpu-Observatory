"""Model registry, deployment, inference and batching schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import DataFreshness, ORMModel


class ModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    version: str = Field(default="1.0.0", max_length=60)
    display_name: str | None = Field(default=None, max_length=200)
    framework: str = Field(
        default="vllm",
        pattern="^(vllm|tensorrt_llm|triton|pytorch|onnx|tensorflow|other)$",
    )
    parameter_count_b: float | None = Field(default=None, ge=0, le=100000)
    quantization: str = Field(default="fp16", pattern="^(none|fp16|bf16|fp8|int8|int4|awq|gptq)$")
    context_length: int | None = Field(default=None, ge=1, le=100_000_000)
    max_batch_size: int | None = Field(default=None, ge=1, le=8192)
    preferred_batch_sizes: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=4000)
    tags: str | None = Field(default=None, max_length=300)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Model name cannot be blank.")
        return cleaned


class ModelUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    tags: str | None = Field(default=None, max_length=300)
    max_batch_size: int | None = Field(default=None, ge=1, le=8192)
    is_active: bool | None = None


class ModelOut(ORMModel):
    id: str
    name: str
    version: str
    display_name: str | None = None
    framework: str
    parameter_count_b: float | None = None
    quantization: str
    context_length: int | None = None
    max_batch_size: int | None = None
    preferred_batch_sizes: str | None = None
    description: str | None = None
    tags: str | None = None
    is_active: bool
    data_source: str
    created_at: datetime


class DeploymentCreate(BaseModel):
    model_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=200)
    environment: str = Field(default="production", max_length=40)
    gpu_id: str | None = Field(default=None, max_length=36)
    gpu_count: int = Field(default=1, ge=1, le=1024)
    endpoint_url: str | None = Field(default=None, max_length=400)
    backend: str = Field(default="local", pattern="^(local|vllm|triton|openai)$")
    replicas: int = Field(default=1, ge=1, le=1000)
    max_batch_size: int | None = Field(default=None, ge=1, le=8192)
    batch_window_ms: float | None = Field(default=None, ge=0, le=10000)
    tensor_parallel_size: int | None = Field(default=None, ge=1, le=128)


class DeploymentOut(ORMModel):
    id: str
    model_id: str
    name: str
    environment: str
    gpu_id: str | None = None
    gpu_count: int
    endpoint_url: str | None = None
    backend: str
    replicas: int
    max_batch_size: int | None = None
    batch_window_ms: float | None = None
    tensor_parallel_size: int | None = None
    status: str
    model_load_time_ms: float | None = None
    data_source: str
    created_at: datetime


class LatencyPercentiles(BaseModel):
    p50: float | None = None
    p90: float | None = None
    p95: float | None = None
    p99: float | None = None
    avg: float | None = None
    min: float | None = None
    max: float | None = None


class LatencyBreakdown(BaseModel):
    queue_ms: float | None = None
    preprocess_ms: float | None = None
    execution_ms: float | None = None
    postprocess_ms: float | None = None


class LatencyBucket(BaseModel):
    """One bar of the latency distribution histogram."""

    lower_ms: float
    upper_ms: float | None = None
    count: int


class InferenceSummary(BaseModel):
    data_source: str
    range_label: str
    start: datetime
    end: datetime
    request_count: int = 0
    error_count: int = 0
    # None (not zero) when no requests were observed: an unmeasured
    # error rate is unknown, not perfect.
    error_rate: float | None = None
    requests_per_second: float | None = None
    latency: LatencyPercentiles = Field(default_factory=LatencyPercentiles)
    breakdown: LatencyBreakdown = Field(default_factory=LatencyBreakdown)
    tokens_per_second: float | None = None
    input_tokens_per_second: float | None = None
    output_tokens_per_second: float | None = None
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    avg_batch_size: float | None = None
    max_batch_size: int | None = None
    batch_efficiency: float | None = None
    avg_concurrency: float | None = None
    freshness: DataFreshness = Field(default_factory=DataFreshness)


class InferenceRequestOut(ORMModel):
    id: str
    deployment_id: str | None = None
    model_id: str | None = None
    started_at: datetime
    total_latency_ms: float
    queue_latency_ms: float | None = None
    execution_latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    batch_size: int | None = None
    concurrency: int | None = None
    status_code: int
    is_error: bool
    error_type: str | None = None
    trace_id: str | None = None


class InferenceRequestIngest(BaseModel):
    """Recorded by the inference gateway for each observed request."""

    deployment_id: str | None = Field(default=None, max_length=36)
    model_id: str | None = Field(default=None, max_length=36)
    gpu_id: str | None = Field(default=None, max_length=36)
    started_at: datetime | None = None
    total_latency_ms: float = Field(ge=0, le=3_600_000)
    queue_latency_ms: float | None = Field(default=None, ge=0, le=3_600_000)
    preprocess_latency_ms: float | None = Field(default=None, ge=0, le=3_600_000)
    execution_latency_ms: float | None = Field(default=None, ge=0, le=3_600_000)
    postprocess_latency_ms: float | None = Field(default=None, ge=0, le=3_600_000)
    time_to_first_token_ms: float | None = Field(default=None, ge=0, le=3_600_000)
    input_tokens: int | None = Field(default=None, ge=0, le=10_000_000)
    output_tokens: int | None = Field(default=None, ge=0, le=10_000_000)
    batch_size: int | None = Field(default=None, ge=1, le=8192)
    concurrency: int | None = Field(default=None, ge=0, le=100000)
    status_code: int = Field(default=200, ge=100, le=599)
    is_error: bool = False
    error_type: str | None = Field(default=None, max_length=120)
    client_id: str | None = Field(default=None, max_length=120)
    trace_id: str | None = Field(default=None, max_length=64)
    data_source: str = Field(default="production", pattern="^(production|demo)$")


class BatchMetricOut(ORMModel):
    id: str
    deployment_id: str | None = None
    bucket_start: datetime
    bucket_seconds: int
    requested_batch_size: float | None = None
    effective_batch_size: float | None = None
    avg_batch_size: float | None = None
    max_batch_size: int | None = None
    configured_max_batch_size: int | None = None
    queue_depth: float | None = None
    batch_formation_ms: float | None = None
    batch_efficiency: float | None = None
    gpu_utilization_pct: float | None = None
    throughput_rps: float | None = None


class BatchAnalysis(BaseModel):
    """Aggregate batching health, including explicit under-batching detection."""

    data_source: str
    avg_batch_size: float | None = None
    max_batch_size: int | None = None
    configured_max_batch_size: int | None = None
    batch_efficiency: float | None = None
    avg_queue_depth: float | None = None
    avg_batch_formation_ms: float | None = None
    avg_gpu_utilization: float | None = None
    throughput_rps: float | None = None
    under_batching_detected: bool = False
    over_batching_detected: bool = False
    headroom_pct: float | None = None
    buckets: list[BatchMetricOut] = Field(default_factory=list)


class ModelPerformance(BaseModel):
    """Per-model rollup used by the Models page and the comparison tool."""

    model_id: str
    model_name: str
    version: str
    quantization: str | None = None
    framework: str | None = None
    request_count: int = 0
    avg_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    p99_latency_ms: float | None = None
    throughput_rps: float | None = None
    tokens_per_second: float | None = None
    avg_batch_size: float | None = None
    batch_efficiency: float | None = None
    error_rate: float | None = None
    avg_gpu_utilization: float | None = None
    avg_vram_used_mb: float | None = None
    cost_per_request: float | None = None
    cost_per_1m_tokens: float | None = None
    has_data: bool = True


class ComparisonDelta(BaseModel):
    metric: str
    label: str
    baseline_value: float | None = None
    candidate_value: float | None = None
    delta_pct: float | None = None
    better: str | None = Field(default=None, description="baseline | candidate | tie | unknown")
    unit: str | None = None
    lower_is_better: bool = True


class ComparisonResponse(BaseModel):
    """Side-by-side comparison. Every number is computed from stored metrics."""

    data_source: str
    range_label: str
    models: list[ModelPerformance]
    deltas: list[ComparisonDelta] = Field(default_factory=list)
    recommendation: str | None = None
    recommended_model_id: str | None = None
    confidence: float | None = None
    caveats: list[str] = Field(default_factory=list)
    generated_at: datetime
