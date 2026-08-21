"""Shared enumerations used across models, schemas and services."""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


class DataSource(StrEnum):
    """Hard separation between real telemetry and synthetic demo telemetry.

    Every telemetry row carries this discriminator, and every read path filters
    on it. Demo data can therefore never be presented as production data.
    """

    PRODUCTION = "production"
    DEMO = "demo"


class UserRole(StrEnum):
    VIEWER = "viewer"
    OPERATOR = "operator"
    ADMIN = "admin"


class Scope(StrEnum):
    """Fine-grained permissions attachable to API keys."""

    TELEMETRY_READ = "telemetry:read"
    TELEMETRY_WRITE = "telemetry:write"
    MODELS_READ = "models:read"
    MODELS_WRITE = "models:write"
    ALERTS_READ = "alerts:read"
    ALERTS_WRITE = "alerts:write"
    DIAGNOSTICS_READ = "diagnostics:read"
    DIAGNOSTICS_RUN = "diagnostics:run"
    AGENT_CHAT = "agent:chat"
    COST_READ = "cost:read"
    ADMIN = "admin"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertState(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class AlertCondition(StrEnum):
    GPU_UTILIZATION_BELOW = "gpu_utilization_below"
    VRAM_ABOVE = "vram_above"
    TEMPERATURE_ABOVE = "temperature_above"
    P95_LATENCY_ABOVE = "p95_latency_above"
    THROUGHPUT_BELOW = "throughput_below"
    ERROR_RATE_ABOVE = "error_rate_above"
    COST_ABOVE = "cost_above"
    POWER_ABOVE = "power_above"


class AnomalyMethod(StrEnum):
    ZSCORE = "zscore"
    EWMA = "ewma"
    PERCENTILE = "percentile"
    ISOLATION_FOREST = "isolation_forest"


class DiagnosisKind(StrEnum):
    GPU_UNDER_UTILIZATION = "gpu_under_utilization"
    VRAM_SATURATION = "vram_saturation"
    CPU_BOTTLENECK = "cpu_bottleneck"
    MEMORY_BOTTLENECK = "memory_bottleneck"
    LATENCY_SPIKE = "latency_spike"
    THROUGHPUT_DEGRADATION = "throughput_degradation"
    EXCESSIVE_QUEUEING = "excessive_queueing"
    UNDER_BATCHING = "under_batching"
    OVER_BATCHING = "over_batching"
    THERMAL_THROTTLING = "thermal_throttling"
    POWER_LIMITATION = "power_limitation"
    HIGH_ERROR_RATE = "high_error_rate"
    MODEL_REGRESSION = "model_regression"
    ABNORMAL_TOKEN_THROUGHPUT = "abnormal_token_throughput"
    COST_SPIKE = "cost_spike"
    HEALTHY = "healthy"


class DiagnosisEngine(StrEnum):
    RULES = "rules"
    LLM = "llm"
    HYBRID = "hybrid"


class ModelFramework(StrEnum):
    VLLM = "vllm"
    TENSORRT_LLM = "tensorrt_llm"
    TRITON = "triton"
    PYTORCH = "pytorch"
    ONNX = "onnx"
    TENSORFLOW = "tensorflow"
    OTHER = "other"


class Quantization(StrEnum):
    NONE = "none"
    FP16 = "fp16"
    BF16 = "bf16"
    FP8 = "fp8"
    INT8 = "int8"
    INT4 = "int4"
    AWQ = "awq"
    GPTQ = "gptq"


class DeploymentStatus(StrEnum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    STOPPED = "stopped"


class WorkloadStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkloadProfile(StrEnum):
    LOW_CONCURRENCY = "low_concurrency"
    HIGH_CONCURRENCY = "high_concurrency"
    SMALL_BATCH = "small_batch"
    LARGE_BATCH = "large_batch"
    LATENCY_SPIKE = "latency_spike"
    MEMORY_PRESSURE = "memory_pressure"


class DemoScenario(StrEnum):
    HEALTHY = "healthy"
    UNDER_BATCHING = "under_batching"
    VRAM_PRESSURE = "vram_pressure"
    CPU_BOTTLENECK = "cpu_bottleneck"
    LATENCY_SPIKE = "latency_spike"
    THROUGHPUT_DEGRADATION = "throughput_degradation"
    THERMAL_THROTTLING = "thermal_throttling"


class PricingKind(StrEnum):
    CLOUD_HOURLY = "cloud_hourly"
    ON_PREM_AMORTIZED = "on_prem_amortized"
    ENERGY = "energy"


class MetricKind(StrEnum):
    GPU_UTILIZATION = "gpu_utilization"
    VRAM_USED = "vram_used"
    VRAM_UTILIZATION = "vram_utilization"
    TEMPERATURE = "temperature"
    POWER = "power"
    CPU_UTILIZATION = "cpu_utilization"
    LATENCY_P95 = "latency_p95"
    THROUGHPUT = "throughput"
    TOKENS_PER_SECOND = "tokens_per_second"
    ERROR_RATE = "error_rate"
    COST = "cost"
    BATCH_SIZE = "batch_size"
