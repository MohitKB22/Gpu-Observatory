#!/usr/bin/env python3
"""Create an administrator account.

The password is read from stdin or the ADMIN_PASSWORD environment variable so
it never appears in shell history or the process list.

Usage:
    python scripts/create_admin.py --email admin@example.com
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))


async def main() -> int:
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", default=None)
    parser.add_argument("--role", default="admin", choices=["viewer", "operator", "admin"])
    args = parser.parse_args()

    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password (min 12 chars): ")
    if len(password) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        return 2

    from app.core.errors import AppError
    from app.db.session import dispose_engine, get_sessionmaker
    from app.schemas.auth import UserCreate
    from app.services.auth_service import create_user

    maker = get_sessionmaker()
    try:
        async with maker() as session:
            user = await create_user(
                session,
                UserCreate(email=args.email, password=password, full_name=args.name, role=args.role),
            )
        print(f"created {args.role}: {user.email} ({user.id})")
        return 0
    except AppError as exc:
        print(f"failed: {exc.message}", file=sys.stderr)
        return 1
    finally:
        await dispose_engine()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
