import uuid
from datetime import datetime

from pydantic import BaseModel


class HostRead(BaseModel):
    cpu_percent: float
    cpu_count: int
    load_average: tuple[float, float, float] | None
    memory_total_bytes: int
    memory_used_bytes: int
    memory_percent: float
    disk_total_bytes: int
    disk_used_bytes: int
    disk_percent: float


class WorkerRead(BaseModel):
    """The backend worker process that served this request."""

    pid: int
    uptime_seconds: float
    cpu_percent: float
    memory_rss_bytes: int
    threads: int
    python_version: str
    configured_workers: int


class GpuDeviceRead(BaseModel):
    index: int
    name: str
    utilization_percent: float | None
    memory_used_bytes: int | None
    memory_total_bytes: int | None
    temperature_celsius: float | None
    power_watts: float | None


class GpuRead(BaseModel):
    available: bool
    source: str | None
    driver_version: str | None
    devices: list[GpuDeviceRead]
    unavailable_reason: str | None


class DatabaseHealthRead(BaseModel):
    ok: bool
    latency_ms: float | None
    server_version: str | None
    error: str | None


class EndpointHealthRead(BaseModel):
    model_id: uuid.UUID
    model_name: str
    provider: str
    is_demo: bool
    is_enabled: bool
    status: str
    last_checked_at: datetime | None
    last_check_latency_ms: float | None
    last_error: str | None


class InferenceServerRead(BaseModel):
    """Live scheduler metrics scraped from a vLLM server's /metrics endpoint."""

    model_id: uuid.UUID
    model_name: str
    reachable: bool
    requests_running: float | None
    requests_waiting: float | None
    kv_cache_usage_percent: float | None
    error: str | None


class InfrastructureResponse(BaseModel):
    sampled_at: datetime
    host: HostRead
    worker: WorkerRead
    gpu: GpuRead
    database: DatabaseHealthRead
    endpoints: list[EndpointHealthRead]
    inference_servers: list[InferenceServerRead]


class UsageSampleRead(BaseModel):
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    process_cpu_percent: float
    gpu_utilization_percent: float | None
    gpu_memory_percent: float | None


class UsageHistoryResponse(BaseModel):
    interval_seconds: float
    samples: list[UsageSampleRead]
