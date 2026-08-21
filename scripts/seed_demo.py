#!/usr/bin/env python3
"""Backfill demo telemetry into the configured database.

Usage:
    python scripts/seed_demo.py --minutes 120 --scenario under_batching --reset
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

os.environ.setdefault("DEMO_MODE", "true")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Seed demo telemetry")
    parser.add_argument("--minutes", type=int, default=90)
    parser.add_argument("--scenario", default=None)
    parser.add_argument("--reset", action="store_true", help="Clear existing demo data first")
    args = parser.parse_args()

    from app.db.session import dispose_engine, get_sessionmaker
    from app.demo.runner import backfill, reset_demo_data
    from app.demo.scenarios import SCENARIOS

    if args.scenario and args.scenario not in SCENARIOS:
        print(f"Unknown scenario '{args.scenario}'. Available: {', '.join(SCENARIOS)}")
        return 2

    maker = get_sessionmaker()
    async with maker() as session:
        if args.reset:
            await reset_demo_data(session)
            print("cleared existing demo data (production telemetry untouched)")
        result = await backfill(session, minutes=args.minutes, scenario=args.scenario)

    print(
        f"seeded {result['gpu_samples']} GPU samples and {result['requests']} requests "
        f"across {result['steps']} buckets"
    )
    await dispose_engine()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
