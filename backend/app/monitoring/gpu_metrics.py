"""GPU metrics from NVIDIA NVML, falling back to nvidia-smi.

When neither is available the report says so (available=False with a reason). We never
substitute placeholder numbers: a dashboard showing invented GPU load is worse than one
showing "unavailable".
"""

import logging
import shutil
import subprocess
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

NVIDIA_SMI_TIMEOUT_SECONDS = 3
_SMI_QUERY_FIELDS = "index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw,driver_version"
_MIB = 1024 * 1024


@dataclass(frozen=True)
class GpuDevice:
    index: int
    name: str
    utilization_percent: float | None
    memory_used_bytes: int | None
    memory_total_bytes: int | None
    temperature_celsius: float | None
    power_watts: float | None


@dataclass(frozen=True)
class GpuReport:
    available: bool
    source: str | None = None  # "nvml" or "nvidia-smi"
    driver_version: str | None = None
    devices: list[GpuDevice] = field(default_factory=list)
    unavailable_reason: str | None = None


class GpuMonitor:
    def __init__(self, nvidia_smi_path: str = "nvidia-smi"):
        self._nvidia_smi_path = nvidia_smi_path
        self._nvml = _load_nvml()

    def read(self) -> GpuReport:
        if self._nvml is not None:
            try:
                return _read_with_nvml(self._nvml)
            except Exception as exc:  # NVML raises its own exception hierarchy
                logger.warning("NVML read failed; trying nvidia-smi", extra={"error": str(exc)})

        smi_path = shutil.which(self._nvidia_smi_path)
        if smi_path is None:
            return GpuReport(
                available=False,
                unavailable_reason=(
                    "No NVIDIA driver detected: NVML could not be loaded and nvidia-smi is not installed."
                ),
            )
        try:
            return _read_with_nvidia_smi(smi_path)
        except (subprocess.SubprocessError, OSError, ValueError) as exc:
            return GpuReport(available=False, unavailable_reason=f"nvidia-smi failed: {exc}")


def _load_nvml():
    try:
        import pynvml

        pynvml.nvmlInit()
        return pynvml
    except Exception:  # library missing, driver missing, or no GPU
        return None


def _read_with_nvml(nvml) -> GpuReport:
    devices = []
    for index in range(nvml.nvmlDeviceGetCount()):
        handle = nvml.nvmlDeviceGetHandleByIndex(index)
        name = nvml.nvmlDeviceGetName(handle)
        memory = nvml.nvmlDeviceGetMemoryInfo(handle)
        devices.append(
            GpuDevice(
                index=index,
                name=name.decode() if isinstance(name, bytes) else name,
                utilization_percent=float(nvml.nvmlDeviceGetUtilizationRates(handle).gpu),
                memory_used_bytes=int(memory.used),
                memory_total_bytes=int(memory.total),
                temperature_celsius=_optional(nvml.nvmlDeviceGetTemperature, handle, nvml.NVML_TEMPERATURE_GPU),
                power_watts=_milliwatts_to_watts(_optional(nvml.nvmlDeviceGetPowerUsage, handle)),
            )
        )
    driver = nvml.nvmlSystemGetDriverVersion()
    return GpuReport(
        available=bool(devices),
        source="nvml",
        driver_version=driver.decode() if isinstance(driver, bytes) else driver,
        devices=devices,
        unavailable_reason=None if devices else "NVML loaded but reported no GPUs.",
    )


def _read_with_nvidia_smi(smi_path: str) -> GpuReport:
    output = subprocess.run(
        [smi_path, f"--query-gpu={_SMI_QUERY_FIELDS}", "--format=csv,noheader,nounits"],
        capture_output=True,
        text=True,
        timeout=NVIDIA_SMI_TIMEOUT_SECONDS,
        check=True,
    ).stdout
    return parse_nvidia_smi_output(output)


def parse_nvidia_smi_output(output: str) -> GpuReport:
    devices = []
    driver_version = None
    for line in output.strip().splitlines():
        index, name, utilization, mem_used, mem_total, temperature, power, driver_version = (
            part.strip() for part in line.split(",")
        )
        devices.append(
            GpuDevice(
                index=int(index),
                name=name,
                utilization_percent=_smi_number(utilization),
                memory_used_bytes=_mib_to_bytes(_smi_number(mem_used)),
                memory_total_bytes=_mib_to_bytes(_smi_number(mem_total)),
                temperature_celsius=_smi_number(temperature),
                power_watts=_smi_number(power),
            )
        )
    if not devices:
        return GpuReport(available=False, source="nvidia-smi", unavailable_reason="nvidia-smi reported no GPUs.")
    return GpuReport(available=True, source="nvidia-smi", driver_version=driver_version, devices=devices)


def _smi_number(value: str) -> float | None:
    # nvidia-smi prints "[N/A]" or "[Not Supported]" for fields a card does not expose.
    try:
        return float(value)
    except ValueError:
        return None


def _mib_to_bytes(value: float | None) -> int | None:
    return int(value * _MIB) if value is not None else None


def _optional(read, *args) -> float | None:
    """Some cards do not expose temperature or power; NVML raises for those fields."""
    try:
        return float(read(*args))
    except Exception:
        return None


def _milliwatts_to_watts(value: float | None) -> float | None:
    return value / 1000 if value is not None else None
