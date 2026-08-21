"""Standalone telemetry agent.

Runs on a GPU node, collects NVML/DCGM and host metrics locally, and pushes
them to the Observatory API. Deploy this as a DaemonSet so each node reports
its own hardware.

Authenticates with an API key holding the `telemetry:write` scope.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

# Reuse the collectors from the API package so there is one implementation.
sys.path.insert(0, os.environ.get("NVO_API_PATH", "/opt/nvo-api"))

try:
    from app.collectors.dcgm import DcgmCollector
    from app.collectors.nvml import NvmlCollector
    from app.collectors.system import SystemCollector
except ImportError:  # pragma: no cover - surfaced at runtime with guidance
    print(
        "Cannot import the collector package. Set NVO_API_PATH to the directory "
        "containing the `app` package (the API image mounts it at /opt/nvo-api).",
        file=sys.stderr,
    )
    raise

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}',
)
logger = logging.getLogger("telemetry-agent")

_running = True


def _stop(_signum: int, _frame: Any) -> None:
    global _running
    _running = False
    logger.info("shutdown requested")


class Agent:
    def __init__(self, api_url: str, api_key: str, interval: float, host: str, data_source: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.interval = max(1.0, interval)
        self.host = host
        self.data_source = data_source

        self.nvml = NvmlCollector()
        self.dcgm = DcgmCollector() if os.environ.get("DCGM_ENABLED") == "true" else None
        self.system = SystemCollector(host=host)

        status = self.nvml.status()
        logger.info(
            "collectors initialised: nvml=%s reason=%s system=%s",
            status.available,
            status.reason,
            self.system.status().available,
        )

    def collect(self) -> dict[str, Any]:
        samples = []
        if self.nvml.status().available:
            samples = self.nvml.sample()
        elif self.dcgm is not None:
            samples = self.dcgm.sample()

        payload: dict[str, Any] = {
            "host": self.host,
            "collected_at": datetime.now(timezone.utc).isoformat(),
            "data_source": self.data_source,
            "gpus": [
                {
                    "uuid": s.uuid,
                    "index": s.index,
                    "utilization_pct": s.utilization_pct,
                    "memory_utilization_pct": s.memory_utilization_pct,
                    "memory_used_mb": s.memory_used_mb,
                    "memory_free_mb": s.memory_free_mb,
                    "memory_total_mb": s.memory_total_mb,
                    "temperature_c": s.temperature_c,
                    "power_w": s.power_w,
                    "power_limit_w": s.power_limit_w,
                    "sm_clock_mhz": s.sm_clock_mhz,
                    "memory_clock_mhz": s.memory_clock_mhz,
                    "fan_speed_pct": s.fan_speed_pct,
                    "throttle_reasons": s.throttle_reasons,
                }
                for s in samples
            ],
        }

        system_sample = self.system.sample()
        if system_sample is not None:
            data = asdict(system_sample)
            data.pop("recorded_at", None)
            payload["system"] = data
        return payload

    def push(self, payload: dict[str, Any]) -> bool:
        request = urllib.request.Request(
            f"{self.api_url}/api/v1/telemetry/ingest",
            data=json.dumps(payload, default=str).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return 200 <= response.status < 300
        except urllib.error.HTTPError as exc:
            logger.error("ingest rejected: status=%s body=%s", exc.code, exc.read()[:200])
        except Exception as exc:
            logger.error("ingest failed: %s", str(exc)[:200])
        return False

    def run(self) -> None:
        logger.info(
            "agent started: api=%s host=%s interval=%.1fs", self.api_url, self.host, self.interval
        )
        failures = 0
        while _running:
            started = time.monotonic()
            try:
                payload = self.collect()
                if self.push(payload):
                    failures = 0
                    logger.info("pushed %d gpu sample(s)", len(payload["gpus"]))
                else:
                    failures += 1
            except Exception as exc:
                failures += 1
                logger.exception("collection cycle failed: %s", str(exc)[:200])

            # Back off on sustained failure so a downed API is not hammered.
            delay = self.interval * min(8, 2 ** min(failures, 3)) if failures else self.interval
            elapsed = time.monotonic() - started
            time.sleep(max(0.5, delay - elapsed))

        self.nvml.shutdown()
        logger.info("agent stopped")


def main() -> int:
    parser = argparse.ArgumentParser(description="NVIDIA AI Performance Observatory telemetry agent")
    parser.add_argument("--api-url", default=os.environ.get("NVO_API_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("NVO_API_KEY", ""))
    parser.add_argument(
        "--interval", type=float, default=float(os.environ.get("TELEMETRY_INTERVAL_SECONDS", "5"))
    )
    parser.add_argument("--host", default=os.environ.get("NODE_NAME", socket.gethostname()))
    parser.add_argument(
        "--data-source", default=os.environ.get("DATA_SOURCE", "production"),
        choices=["production", "demo"],
    )
    args = parser.parse_args()

    if not args.api_key:
        logger.error("NVO_API_KEY is required (an API key with the telemetry:write scope)")
        return 2

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    Agent(args.api_url, args.api_key, args.interval, args.host, args.data_source).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
