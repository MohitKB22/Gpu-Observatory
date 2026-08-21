"""Collector interfaces and sample dataclasses."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class GpuDeviceInfo:
    """Static properties of a discovered device."""

    uuid: str
    index: int
    name: str
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


@dataclass
class GpuSample:
    """One dynamic telemetry reading for a device."""

    uuid: str
    index: int
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
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
    throttle_reasons: list[str] = field(default_factory=list)
    ecc_errors: int | None = None
    processes: list[GpuProcessSample] = field(default_factory=list)


@dataclass
class GpuProcessSample:
    pid: int
    process_name: str | None = None
    used_memory_mb: float | None = None
    sm_utilization_pct: float | None = None
    workload_label: str | None = None


@dataclass
class SystemSample:
    recorded_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    host: str = "localhost"
    cpu_utilization_pct: float | None = None
    per_core_utilization: list[float] = field(default_factory=list)
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


@dataclass
class CollectorStatus:
    """Why a collector is or is not producing data -- surfaced to the UI."""

    available: bool
    reason: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


class GpuCollector(ABC):
    """Interface implemented by NVML, DCGM and demo collectors."""

    name: str = "abstract"

    @abstractmethod
    def status(self) -> CollectorStatus: ...

    @abstractmethod
    def discover(self) -> list[GpuDeviceInfo]: ...

    @abstractmethod
    def sample(self) -> list[GpuSample]: ...

    def shutdown(self) -> None:  # pragma: no cover - trivial default
        return None
