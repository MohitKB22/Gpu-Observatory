"""Background sampler that keeps a short in-memory history of host, process and GPU usage.

The history lives in process memory, so it resets on restart and each uvicorn worker keeps
its own copy. Long-term retention belongs in Prometheus (see /metrics).
"""

import asyncio
import contextlib
import logging
import time
from collections import deque
from dataclasses import dataclass

import psutil

from app.monitoring.gpu_metrics import GpuMonitor, GpuReport

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageSample:
    timestamp: float
    cpu_percent: float
    memory_percent: float
    process_cpu_percent: float
    gpu_utilization_percent: float | None  # mean across GPUs, None when no GPU is visible
    gpu_memory_percent: float | None


class SystemSampler:
    def __init__(self, gpu_monitor: GpuMonitor, interval_seconds: float, history_size: int):
        self._gpu_monitor = gpu_monitor
        self._interval = interval_seconds
        self._history: deque[UsageSample] = deque(maxlen=history_size)
        self._process = psutil.Process()
        self._task: asyncio.Task | None = None
        self.latest_gpu_report: GpuReport | None = None
        # Prime psutil's CPU counters so the first real sample measures a real interval.
        psutil.cpu_percent(interval=None)
        self._process.cpu_percent(interval=None)

    @property
    def process(self) -> psutil.Process:
        return self._process

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="system-sampler")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    def latest(self) -> UsageSample:
        """Most recent sample, taking one immediately if none exists yet."""
        if not self._history:
            self.take_sample()
        return self._history[-1]

    def history(self) -> list[UsageSample]:
        return list(self._history)

    def take_sample(self) -> UsageSample:
        gpu_report = self._gpu_monitor.read()
        self.latest_gpu_report = gpu_report
        sample = UsageSample(
            timestamp=time.time(),
            cpu_percent=psutil.cpu_percent(interval=None),
            memory_percent=psutil.virtual_memory().percent,
            process_cpu_percent=self._process.cpu_percent(interval=None),
            gpu_utilization_percent=_mean_gpu_utilization(gpu_report),
            gpu_memory_percent=_gpu_memory_percent(gpu_report),
        )
        self._history.append(sample)
        return sample

    async def _run(self) -> None:
        while True:
            try:
                # nvidia-smi is a subprocess call, so keep it off the event loop.
                await asyncio.to_thread(self.take_sample)
            except Exception:
                logger.exception("System sampling failed")
            await asyncio.sleep(self._interval)


def _mean_gpu_utilization(report: GpuReport) -> float | None:
    values = [d.utilization_percent for d in report.devices if d.utilization_percent is not None]
    return sum(values) / len(values) if values else None


def _gpu_memory_percent(report: GpuReport) -> float | None:
    used = sum(d.memory_used_bytes or 0 for d in report.devices)
    total = sum(d.memory_total_bytes or 0 for d in report.devices)
    return used / total * 100 if total else None
