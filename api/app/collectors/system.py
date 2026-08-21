"""Host CPU / memory / disk / network collector built on psutil."""

from __future__ import annotations

import contextlib
import socket
import time
from datetime import datetime, timezone

from app.collectors.base import CollectorStatus, SystemSample
from app.core.logging import get_logger

logger = get_logger(__name__)


class SystemCollector:
    """Collects host metrics. Network rates are derived between calls."""

    name = "system"

    def __init__(self, host: str | None = None) -> None:
        self.host = host or socket.gethostname()
        self._psutil = None
        self._last_net: tuple[float, float, float] | None = None
        self._status = CollectorStatus(False, "not_initialised")
        try:
            import psutil

            self._psutil = psutil
            self._status = CollectorStatus(True)
            # Prime the non-blocking CPU percentage counter.
            psutil.cpu_percent(interval=None)
            psutil.cpu_percent(interval=None, percpu=True)
        except ImportError:
            self._status = CollectorStatus(False, "psutil_not_installed")
            logger.warning("system_collector_unavailable", reason="psutil_not_installed")

    def status(self) -> CollectorStatus:
        return self._status

    def sample(self) -> SystemSample | None:
        if self._psutil is None:
            return None
        psutil = self._psutil
        sample = SystemSample(recorded_at=datetime.now(timezone.utc), host=self.host)

        try:
            sample.cpu_utilization_pct = float(psutil.cpu_percent(interval=None))
            sample.per_core_utilization = [
                float(v) for v in psutil.cpu_percent(interval=None, percpu=True)
            ]
            sample.core_count = psutil.cpu_count(logical=True)
        except Exception as exc:
            logger.warning("cpu_sample_failed", error=str(exc)[:160])

        try:
            load1, load5, load15 = psutil.getloadavg()
            sample.load_avg_1m, sample.load_avg_5m, sample.load_avg_15m = (
                float(load1),
                float(load5),
                float(load15),
            )
        except (AttributeError, OSError):
            pass  # Not available on every platform.

        try:
            vm = psutil.virtual_memory()
            sample.ram_total_mb = vm.total / 1024**2
            sample.ram_used_mb = (vm.total - vm.available) / 1024**2
            sample.ram_utilization_pct = float(vm.percent)
            swap = psutil.swap_memory()
            sample.swap_total_mb = swap.total / 1024**2
            sample.swap_used_mb = swap.used / 1024**2
        except Exception as exc:
            logger.warning("memory_sample_failed", error=str(exc)[:160])

        try:
            disk = psutil.disk_usage("/")
            sample.disk_total_gb = disk.total / 1024**3
            sample.disk_used_gb = disk.used / 1024**3
            sample.disk_utilization_pct = float(disk.percent)
        except Exception as exc:
            logger.warning("disk_sample_failed", error=str(exc)[:160])

        try:
            net = psutil.net_io_counters()
            now = time.monotonic()
            if self._last_net is not None:
                prev_time, prev_sent, prev_recv = self._last_net
                elapsed = max(1e-6, now - prev_time)
                sample.net_sent_kb_s = max(0.0, (net.bytes_sent - prev_sent) / elapsed / 1024)
                sample.net_recv_kb_s = max(0.0, (net.bytes_recv - prev_recv) / elapsed / 1024)
            self._last_net = (now, float(net.bytes_sent), float(net.bytes_recv))
        except Exception as exc:
            logger.warning("network_sample_failed", error=str(exc)[:160])

        with contextlib.suppress(Exception):
            sample.process_count = len(psutil.pids())

        return sample
