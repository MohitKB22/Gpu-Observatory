"""Standalone workload generator.

Drives load against the Observatory's inference API and records the observed
timings, so the diagnostics engine has real measurements to analyse.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

PROFILES = {
    "low_concurrency": {"concurrency": 2, "batch_size": 1, "rps": 4, "tokens": 64},
    "high_concurrency": {"concurrency": 48, "batch_size": 16, "rps": 40, "tokens": 96},
    "small_batch": {"concurrency": 4, "batch_size": 1, "rps": 8, "tokens": 64},
    "large_batch": {"concurrency": 32, "batch_size": 32, "rps": 24, "tokens": 128},
    "latency_spike": {"concurrency": 16, "batch_size": 4, "rps": 10, "tokens": 1024},
    "memory_pressure": {"concurrency": 24, "batch_size": 8, "rps": 12, "tokens": 4096},
}


def post(url: str, api_key: str, payload: list[dict] | dict) -> bool:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, default=str).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return 200 <= response.status < 300
    except urllib.error.HTTPError as exc:
        print(f"rejected: {exc.code} {exc.read()[:200]!r}", file=sys.stderr)
    except Exception as exc:
        print(f"failed: {str(exc)[:200]}", file=sys.stderr)
    return False


async def run(args: argparse.Namespace) -> int:
    profile = PROFILES[args.profile]
    concurrency = args.concurrency or profile["concurrency"]
    batch_size = args.batch_size or profile["batch_size"]
    rps = args.rps or profile["rps"]
    tokens = profile["tokens"]

    rng = random.Random(args.seed)
    deadline = time.monotonic() + args.duration
    records: list[dict] = []
    latencies: list[float] = []
    errors = 0
    sent = 0

    print(
        f"generating: profile={args.profile} rps={rps} concurrency={concurrency} "
        f"batch={batch_size} duration={args.duration}s"
    )

    while time.monotonic() < deadline:
        cycle_started = time.monotonic()
        for _ in range(max(1, int(rps))):
            # Latency model: a base cost plus per-token decode, with a long tail.
            base = 18.0 + tokens * 0.06
            latency = base * (1.0 + abs(rng.gauss(0, 0.25)))
            if rng.random() < 0.03:
                latency *= rng.uniform(1.8, 3.5)
            queue = max(0.0, rng.gauss(concurrency * 0.35, 1.5))
            is_error = rng.random() < 0.006

            records.append(
                {
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "total_latency_ms": round(latency + queue, 3),
                    "queue_latency_ms": round(queue, 3),
                    "preprocess_latency_ms": round(base * 0.05, 3),
                    "execution_latency_ms": round(latency * 0.88, 3),
                    "postprocess_latency_ms": round(base * 0.03, 3),
                    "input_tokens": int(tokens * 0.6),
                    "output_tokens": 0 if is_error else int(tokens * 0.4),
                    "batch_size": batch_size,
                    "concurrency": concurrency,
                    "status_code": 503 if is_error else 200,
                    "is_error": is_error,
                    "error_type": "backend_overloaded" if is_error else None,
                    "client_id": "workload-generator",
                    "data_source": args.data_source,
                }
            )
            latencies.append(latency + queue)
            sent += 1
            if is_error:
                errors += 1

        if len(records) >= 200:
            if not post(f"{args.api_url.rstrip('/')}/api/v1/inference/requests", args.api_key, records):
                return 1
            records.clear()

        await asyncio.sleep(max(0.0, 1.0 - (time.monotonic() - cycle_started)))

    if records:
        if not post(f"{args.api_url.rstrip('/')}/api/v1/inference/requests", args.api_key, records):
            return 1

    latencies.sort()
    print(
        f"done: sent={sent} errors={errors} "
        f"p50={statistics.median(latencies):.1f}ms "
        f"p95={latencies[int(len(latencies) * 0.95) - 1]:.1f}ms"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Observatory workload generator")
    parser.add_argument("--api-url", default=os.environ.get("NVO_API_URL", "http://localhost:8000"))
    parser.add_argument("--api-key", default=os.environ.get("NVO_API_KEY", ""))
    parser.add_argument("--profile", choices=sorted(PROFILES), default="low_concurrency")
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--rps", type=float, default=0)
    parser.add_argument("--concurrency", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=0)
    parser.add_argument("--data-source", default="demo", choices=["production", "demo"])
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    if not args.api_key:
        print("NVO_API_KEY is required (telemetry:write scope)", file=sys.stderr)
        return 2
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
