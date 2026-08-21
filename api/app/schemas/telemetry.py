"""GPU and system telemetry schemas."""

from __future__ import annotations

import json
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import DataFreshness, ORMModel


class GpuOut(ORMModel):
    id: str
    uuid: str
    index: int
    name: str
    host: str
    driver_version: str | None = None
    cuda_version: str | None = None
    vbios_version: str | None = None
    serial: str | None = None
    total_memory_mb: float | None = None
    power_limit_w: float | None = None
    max_clock_mhz: int | None = None
    max_memory_clock_mhz: int | None = None
    compute_capability: str | None = None
    pcie_gen: int | None = None
    pcie_width: int | None = None
    data_source: str
    is_available: bool
    last_seen_at: datetime | None = None


class GpuMetricOut(ORMModel):
    id: str
    gpu_id: str
    recorded_at: datetime
    data_source: str
    utilization_pct: float | None = None
    memory_utilization_pct: float | None = None
    memory_used_mb: float | None = None
    memory_free_mb: float | None = None
    memory_total_mb: float | None = None
    temperature_c: float | None = None
    power_w: float | None = None
    power_limit_w: float | None = None
    sm_clock_mhz: int | None = None
    memory_clock_mhz: int | None = None
    fan_speed_pct: float | None = None
    pcie_tx_kb_s: float | None = None
    pcie_rx_kb_s: float | None = None
    throttle_reasons: str | None = None
    ecc_errors: int | None = None


class GpuProcessOut(ORMModel):
    id: str
    gpu_id: str
    recorded_at: datetime
    pid: int
    process_name: str | None = None
    used_memory_mb: float | None = None
    sm_utilization_pct: float | None = None
    workload_label: str | None = None


class GpuDetail(BaseModel):
    """A GPU plus its most recent sample and process table."""

    gpu: GpuOut
    latest: GpuMetricOut | None = None
    processes: list[GpuProcessOut] = Field(default_factory=list)
    freshness: DataFreshness = Field(default_factory=DataFreshness)


class GpuAvailability(BaseModel):
    """Explicit, honest reporting of NVIDIA hardware availability.

    When no NVIDIA GPU is present the API says so plainly rather than
    fabricating hardware statistics.
    """

    nvml_available: bool
    dcgm_available: bool
    gpu_count: int
    reason: str | None = None
    demo_mode: bool
    driver_version: str | None = None
    cuda_version: str | None = None


class SystemMetricOut(ORMModel):
    id: str
    host: str
    recorded_at: datetime
    data_source: str
    cpu_utilization_pct: float | None = None
    per_core_utilization: list[float] | None = None
    core_count: int | None = None
    load_avg_1m: float | None = None
    load_avg_5m: float | None = None
    load_avg_15m: float | None = None
    ram_total_mb: float | None = None
    ram_used_mb: float | None = None
    ram_utilization_pct: float | None = None
    swap_total_mb: float | None = None
    swap_used_mb: float | None = None
    disk_total_gb: float | None = None
    disk_used_gb: float | None = None
    disk_utilization_pct: float | None = None
    net_sent_kb_s: float | None = None
    net_recv_kb_s: float | None = None
    process_count: int | None = None

    @field_validator("per_core_utilization", mode="before")
    @classmethod
    def _parse_per_core(cls, value: object) -> list[float] | None:
        """The column stores a JSON array as text for portability; decode it
        here so every caller of this schema gets a real list."""
        if value is None or isinstance(value, list):
            return value  # type: ignore[return-value]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return None
            return [float(v) for v in parsed] if isinstance(parsed, list) else None
        return None


class SystemSnapshot(BaseModel):
    latest: SystemMetricOut | None = None
    freshness: DataFreshness = Field(default_factory=DataFreshness)


class TelemetryIngest(BaseModel):
    """Payload accepted from remote telemetry agents."""

    host: str = Field(default="localhost", max_length=200)
    collected_at: datetime | None = None
    gpus: list[dict] = Field(default_factory=list, max_length=64)
    system: dict | None = None
    data_source: str = Field(default="production", pattern="^(production|demo)$")


class KpiValue(BaseModel):
    key: str
    label: str
    value: float | None = None
    unit: str | None = None
    delta_pct: float | None = None
    trend: str | None = Field(default=None, description="up | down | flat")
    is_estimate: bool = False
    healthy: bool | None = None


class OverviewResponse(BaseModel):
    data_source: str
    demo_mode: bool
    demo_scenario: str | None = None
    kpis: list[KpiValue]
    gpu_available: GpuAvailability
    active_alert_count: int
    latest_diagnosis_id: str | None = None
    freshness: DataFreshness
    generated_at: datetime
