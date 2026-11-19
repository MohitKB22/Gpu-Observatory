"""Host and process metrics from psutil.

Inside a container psutil reads the kernel's view, so CPU count and total memory describe the
host machine rather than any cgroup limit placed on the container.
"""

import os
import platform
import time
from dataclasses import dataclass

import psutil


@dataclass(frozen=True)
class HostMetrics:
    cpu_percent: float
    cpu_count: int
    load_average: tuple[float, float, float] | None
    memory_total_bytes: int
    memory_used_bytes: int
    memory_percent: float
    disk_total_bytes: int
    disk_used_bytes: int
    disk_percent: float


@dataclass(frozen=True)
class ProcessMetrics:
    pid: int
    uptime_seconds: float
    cpu_percent: float
    memory_rss_bytes: int
    threads: int
    python_version: str


def read_host_metrics(cpu_percent: float) -> HostMetrics:
    """`cpu_percent` comes from the sampler: psutil measures CPU between successive calls,
    so a one-off call here would either block or return a meaningless 0.0."""
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    load_average = os.getloadavg() if hasattr(os, "getloadavg") else None
    return HostMetrics(
        cpu_percent=cpu_percent,
        cpu_count=psutil.cpu_count() or 0,
        load_average=load_average,
        memory_total_bytes=memory.total,
        memory_used_bytes=memory.total - memory.available,
        memory_percent=memory.percent,
        disk_total_bytes=disk.total,
        disk_used_bytes=disk.used,
        disk_percent=disk.percent,
    )


def read_process_metrics(process: psutil.Process, cpu_percent: float) -> ProcessMetrics:
    with process.oneshot():
        return ProcessMetrics(
            pid=process.pid,
            uptime_seconds=time.time() - process.create_time(),
            cpu_percent=cpu_percent,
            memory_rss_bytes=process.memory_info().rss,
            threads=process.num_threads(),
            python_version=platform.python_version(),
        )
