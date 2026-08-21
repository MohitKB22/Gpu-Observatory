"""NVIDIA NVML collector.

If NVML or NVIDIA hardware is unavailable the collector reports that plainly
via :meth:`status` and returns no samples. It never fabricates readings.
"""

from __future__ import annotations

import contextlib
import threading
from datetime import datetime, timezone
from typing import Any

from app.collectors.base import (
    CollectorStatus,
    GpuCollector,
    GpuDeviceInfo,
    GpuProcessSample,
    GpuSample,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

_THROTTLE_BITS = [
    (0x0000000001, "gpu_idle"),
    (0x0000000002, "applications_clocks_setting"),
    (0x0000000004, "sw_power_cap"),
    (0x0000000008, "hw_slowdown"),
    (0x0000000010, "sync_boost"),
    (0x0000000020, "sw_thermal_slowdown"),
    (0x0000000040, "hw_thermal_slowdown"),
    (0x0000000080, "hw_power_brake_slowdown"),
    (0x0000000100, "display_clock_setting"),
]


def _decode_throttle(bitmask: int) -> list[str]:
    return [label for bit, label in _THROTTLE_BITS if bitmask & bit]


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class NvmlCollector(GpuCollector):
    name = "nvml"

    def __init__(self) -> None:
        self._nvml: Any = None
        self._initialised = False
        self._status = CollectorStatus(False, "not_initialised")
        self._lock = threading.Lock()
        self._driver_version: str | None = None
        self._cuda_version: str | None = None
        self._initialise()

    # ------------------------------------------------------------ startup ---
    def _initialise(self) -> None:
        try:
            import pynvml  # type: ignore
        except ImportError:
            try:
                from nvidia_ml_py import pynvml  # type: ignore
            except ImportError:
                self._status = CollectorStatus(
                    False,
                    "nvml_library_not_installed",
                    {"hint": "Install nvidia-ml-py to enable NVIDIA telemetry."},
                )
                logger.info("nvml_unavailable", reason="library_not_installed")
                return
        try:
            pynvml.nvmlInit()
        except Exception as exc:
            self._status = CollectorStatus(
                False,
                "nvml_init_failed",
                {
                    "error": str(exc)[:200],
                    "hint": (
                        "No NVIDIA driver or GPU detected on this host. "
                        "GPU telemetry is disabled; enable Demo Mode to explore "
                        "the platform without NVIDIA hardware."
                    ),
                },
            )
            logger.info("nvml_unavailable", reason="init_failed", error=str(exc)[:200])
            return

        self._nvml = pynvml
        self._initialised = True
        try:
            self._driver_version = _text(pynvml.nvmlSystemGetDriverVersion())
        except Exception:
            self._driver_version = None
        try:
            raw = pynvml.nvmlSystemGetCudaDriverVersion()
            self._cuda_version = f"{raw // 1000}.{(raw % 1000) // 10}"
        except Exception:
            self._cuda_version = None

        try:
            count = pynvml.nvmlDeviceGetCount()
        except Exception as exc:  # pragma: no cover - driver edge case
            count = 0
            logger.warning("nvml_device_count_failed", error=str(exc)[:200])

        self._status = CollectorStatus(
            count > 0,
            None if count > 0 else "no_nvidia_gpu_detected",
            {
                "device_count": count,
                "driver_version": self._driver_version,
                "cuda_version": self._cuda_version,
            },
        )
        logger.info("nvml_initialised", device_count=count, driver=self._driver_version)

    # ------------------------------------------------------------- public ---
    def status(self) -> CollectorStatus:
        return self._status

    @property
    def driver_version(self) -> str | None:
        return self._driver_version

    @property
    def cuda_version(self) -> str | None:
        return self._cuda_version

    def discover(self) -> list[GpuDeviceInfo]:
        if not self._initialised or self._nvml is None:
            return []
        nvml = self._nvml
        devices: list[GpuDeviceInfo] = []
        with self._lock:
            try:
                count = nvml.nvmlDeviceGetCount()
            except Exception as exc:
                logger.warning("nvml_count_failed", error=str(exc)[:200])
                return []
            # Enumerate every index; never assume a single device at index 0.
            for index in range(count):
                try:
                    handle = nvml.nvmlDeviceGetHandleByIndex(index)
                    devices.append(self._device_info(nvml, handle, index))
                except Exception as exc:
                    logger.warning("nvml_device_info_failed", index=index, error=str(exc)[:200])
        return devices

    def sample(self) -> list[GpuSample]:
        if not self._initialised or self._nvml is None:
            return []
        nvml = self._nvml
        samples: list[GpuSample] = []
        with self._lock:
            try:
                count = nvml.nvmlDeviceGetCount()
            except Exception:
                return []
            for index in range(count):
                try:
                    handle = nvml.nvmlDeviceGetHandleByIndex(index)
                    samples.append(self._device_sample(nvml, handle, index))
                except Exception as exc:
                    logger.warning("nvml_sample_failed", index=index, error=str(exc)[:200])
        return samples

    def shutdown(self) -> None:
        if self._initialised and self._nvml is not None:
            with contextlib.suppress(Exception):  # pragma: no cover
                self._nvml.nvmlShutdown()
            self._initialised = False

    # ------------------------------------------------------------ helpers ---
    def _device_info(self, nvml: Any, handle: Any, index: int) -> GpuDeviceInfo:
        def safe(fn, default=None):
            try:
                return fn()
            except Exception:
                return default

        memory = safe(lambda: nvml.nvmlDeviceGetMemoryInfo(handle))
        cc = safe(lambda: nvml.nvmlDeviceGetCudaComputeCapability(handle))
        power_limit = safe(lambda: nvml.nvmlDeviceGetEnforcedPowerLimit(handle))

        return GpuDeviceInfo(
            uuid=_text(safe(lambda: nvml.nvmlDeviceGetUUID(handle))) or f"nvml-index-{index}",
            index=index,
            name=_text(safe(lambda: nvml.nvmlDeviceGetName(handle))) or f"NVIDIA GPU {index}",
            driver_version=self._driver_version,
            cuda_version=self._cuda_version,
            vbios_version=_text(safe(lambda: nvml.nvmlDeviceGetVbiosVersion(handle))),
            serial=_text(safe(lambda: nvml.nvmlDeviceGetSerial(handle))),
            total_memory_mb=(memory.total / 1024**2) if memory else None,
            power_limit_w=(power_limit / 1000.0) if power_limit else None,
            max_clock_mhz=safe(lambda: nvml.nvmlDeviceGetMaxClockInfo(handle, nvml.NVML_CLOCK_SM)),
            max_memory_clock_mhz=safe(
                lambda: nvml.nvmlDeviceGetMaxClockInfo(handle, nvml.NVML_CLOCK_MEM)
            ),
            compute_capability=f"{cc[0]}.{cc[1]}" if cc else None,
            pcie_gen=safe(lambda: nvml.nvmlDeviceGetCurrPcieLinkGeneration(handle)),
            pcie_width=safe(lambda: nvml.nvmlDeviceGetCurrPcieLinkWidth(handle)),
        )

    def _device_sample(self, nvml: Any, handle: Any, index: int) -> GpuSample:
        def safe(fn, default=None):
            try:
                return fn()
            except Exception:
                return default

        util = safe(lambda: nvml.nvmlDeviceGetUtilizationRates(handle))
        memory = safe(lambda: nvml.nvmlDeviceGetMemoryInfo(handle))
        power = safe(lambda: nvml.nvmlDeviceGetPowerUsage(handle))
        power_limit = safe(lambda: nvml.nvmlDeviceGetEnforcedPowerLimit(handle))
        throttle = safe(lambda: nvml.nvmlDeviceGetCurrentClocksThrottleReasons(handle), 0)

        processes: list[GpuProcessSample] = []
        for proc in safe(lambda: nvml.nvmlDeviceGetComputeRunningProcesses(handle), []) or []:
            name = safe(lambda p=proc: _text(nvml.nvmlSystemGetProcessName(p.pid)))
            used = getattr(proc, "usedGpuMemory", None)
            processes.append(
                GpuProcessSample(
                    pid=int(proc.pid),
                    process_name=name,
                    used_memory_mb=(used / 1024**2) if used else None,
                )
            )

        return GpuSample(
            uuid=_text(safe(lambda: nvml.nvmlDeviceGetUUID(handle))) or f"nvml-index-{index}",
            index=index,
            recorded_at=datetime.now(timezone.utc),
            utilization_pct=float(util.gpu) if util else None,
            memory_utilization_pct=(
                (memory.used / memory.total * 100.0) if memory and memory.total else None
            ),
            memory_used_mb=(memory.used / 1024**2) if memory else None,
            memory_free_mb=(memory.free / 1024**2) if memory else None,
            memory_total_mb=(memory.total / 1024**2) if memory else None,
            temperature_c=safe(
                lambda: float(nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU))
            ),
            power_w=(power / 1000.0) if power else None,
            power_limit_w=(power_limit / 1000.0) if power_limit else None,
            sm_clock_mhz=safe(lambda: nvml.nvmlDeviceGetClockInfo(handle, nvml.NVML_CLOCK_SM)),
            memory_clock_mhz=safe(lambda: nvml.nvmlDeviceGetClockInfo(handle, nvml.NVML_CLOCK_MEM)),
            fan_speed_pct=safe(lambda: float(nvml.nvmlDeviceGetFanSpeed(handle))),
            pcie_tx_kb_s=safe(
                lambda: float(
                    nvml.nvmlDeviceGetPcieThroughput(handle, nvml.NVML_PCIE_UTIL_TX_BYTES)
                )
            ),
            pcie_rx_kb_s=safe(
                lambda: float(
                    nvml.nvmlDeviceGetPcieThroughput(handle, nvml.NVML_PCIE_UTIL_RX_BYTES)
                )
            ),
            throttle_reasons=_decode_throttle(int(throttle or 0)),
            ecc_errors=safe(
                lambda: nvml.nvmlDeviceGetTotalEccErrors(
                    handle, nvml.NVML_MEMORY_ERROR_TYPE_UNCORRECTED, nvml.NVML_VOLATILE_ECC
                )
            ),
            processes=processes,
        )
