"""DCGM adapter.

Reads the Prometheus exposition endpoint published by dcgm-exporter, which is
the deployment shape used in Kubernetes clusters. Falls back cleanly when the
exporter is not reachable.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import httpx

from app.collectors.base import CollectorStatus, GpuCollector, GpuDeviceInfo, GpuSample
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_SAMPLE_RE = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\{(?P<labels>[^}]*)\}\s+(?P<value>[-+0-9.eE]+)"
)
_LABEL_RE = re.compile(r'(\w+)="([^"]*)"')

# dcgm-exporter field name -> GpuSample attribute
_FIELD_MAP = {
    "DCGM_FI_DEV_GPU_UTIL": "utilization_pct",
    "DCGM_FI_DEV_MEM_COPY_UTIL": "memory_utilization_pct",
    "DCGM_FI_DEV_FB_USED": "memory_used_mb",
    "DCGM_FI_DEV_FB_FREE": "memory_free_mb",
    "DCGM_FI_DEV_FB_TOTAL": "memory_total_mb",
    "DCGM_FI_DEV_GPU_TEMP": "temperature_c",
    "DCGM_FI_DEV_POWER_USAGE": "power_w",
    "DCGM_FI_DEV_ENFORCED_POWER_LIMIT": "power_limit_w",
    "DCGM_FI_DEV_SM_CLOCK": "sm_clock_mhz",
    "DCGM_FI_DEV_MEM_CLOCK": "memory_clock_mhz",
    "DCGM_FI_DEV_FAN_SPEED": "fan_speed_pct",
    "DCGM_FI_PROF_PCIE_TX_BYTES": "pcie_tx_kb_s",
    "DCGM_FI_PROF_PCIE_RX_BYTES": "pcie_rx_kb_s",
}
_INT_FIELDS = {"sm_clock_mhz", "memory_clock_mhz"}


class DcgmCollector(GpuCollector):
    name = "dcgm"

    def __init__(self, endpoint: str | None = None, timeout: float = 3.0) -> None:
        self.endpoint = endpoint or settings.DCGM_ENDPOINT
        self.timeout = timeout
        self._status = CollectorStatus(False, "not_probed")

    def status(self) -> CollectorStatus:
        return self._status

    def _scrape(self) -> str | None:
        try:
            response = httpx.get(self.endpoint, timeout=self.timeout)
            response.raise_for_status()
            self._status = CollectorStatus(True, None, {"endpoint": self.endpoint})
            return response.text
        except Exception as exc:
            self._status = CollectorStatus(
                False,
                "dcgm_exporter_unreachable",
                {"endpoint": self.endpoint, "error": str(exc)[:200]},
            )
            logger.info("dcgm_unreachable", endpoint=self.endpoint, error=str(exc)[:120])
            return None

    def parse(self, payload: str) -> list[GpuSample]:
        """Parse dcgm-exporter text exposition into per-GPU samples."""
        by_gpu: dict[str, GpuSample] = {}
        now = datetime.now(timezone.utc)

        for line in payload.splitlines():
            if not line or line.startswith("#"):
                continue
            match = _SAMPLE_RE.match(line)
            if not match:
                continue
            field = match.group("name")
            attribute = _FIELD_MAP.get(field)
            if attribute is None:
                continue
            labels = dict(_LABEL_RE.findall(match.group("labels")))
            uuid = labels.get("UUID") or labels.get("uuid") or labels.get("gpu")
            if not uuid:
                continue
            try:
                index = int(labels.get("gpu", "0"))
            except ValueError:
                index = 0
            try:
                value = float(match.group("value"))
            except ValueError:
                continue

            sample = by_gpu.setdefault(uuid, GpuSample(uuid=uuid, index=index, recorded_at=now))
            if attribute in ("pcie_tx_kb_s", "pcie_rx_kb_s"):
                value = value / 1024.0  # exporter reports bytes/s
            setattr(sample, attribute, int(value) if attribute in _INT_FIELDS else value)

        for sample in by_gpu.values():
            if (
                sample.memory_utilization_pct is None
                and sample.memory_used_mb is not None
                and sample.memory_total_mb
            ):
                sample.memory_utilization_pct = (
                    sample.memory_used_mb / sample.memory_total_mb * 100.0
                )
        return sorted(by_gpu.values(), key=lambda s: s.index)

    def discover(self) -> list[GpuDeviceInfo]:
        payload = self._scrape()
        if payload is None:
            return []
        return [
            GpuDeviceInfo(
                uuid=sample.uuid,
                index=sample.index,
                name=f"NVIDIA GPU {sample.index}",
                total_memory_mb=sample.memory_total_mb,
                power_limit_w=sample.power_limit_w,
            )
            for sample in self.parse(payload)
        ]

    def sample(self) -> list[GpuSample]:
        payload = self._scrape()
        return self.parse(payload) if payload else []
