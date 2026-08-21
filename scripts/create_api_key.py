#!/usr/bin/env python3
"""Mint an API key for a machine client (telemetry agent, gateway, generator).

The plaintext key is printed once and cannot be retrieved again.

Usage:
    python scripts/create_api_key.py --name telemetry-agent \
        --scopes telemetry:read telemetry:write
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Create an API key")
    parser.add_argument("--name", required=True)
    parser.add_argument("--scopes", nargs="+", default=["telemetry:read", "telemetry:write"])
    parser.add_argument("--expires-in-days", type=int, default=None)
    args = parser.parse_args()

    from app.core.errors import AppError
    from app.db.session import dispose_engine, get_sessionmaker
    from app.schemas.auth import ApiKeyCreate
    from app.services.auth_service import create_api_key

    maker = get_sessionmaker()
    try:
        async with maker() as session:
            api_key, plaintext = await create_api_key(
                session,
                ApiKeyCreate(
                    name=args.name, scopes=args.scopes, expires_in_days=args.expires_in_days
                ),
                owner_id=None,
            )
        print(f"name:   {api_key.name}")
        print(f"scopes: {api_key.scopes}")
        print(f"key:    {plaintext}")
        print("\nStore this now — the plaintext key is not recoverable.")
        return 0
    except AppError as exc:
        print(f"failed: {exc.message}", file=sys.stderr)
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
