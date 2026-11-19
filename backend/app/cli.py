"""Maintenance commands.

python -m app.cli reseed-demo   Regenerate the labelled demo request history now.
python -m app.cli purge-demo    Delete all demo models and demo requests (keeps real data).
                                Set DEMO_MODE=false first, or demo models return on restart.
"""

import argparse
import asyncio

from app.config import get_settings
from app.db.session import create_engine, create_session_factory
from app.logging_config import configure_logging
from app.services.demo_seed import ensure_demo_models, purge_demo_data, refresh_demo_history


async def _reseed_demo() -> None:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            models = await ensure_demo_models(session)
            rows = await refresh_demo_history(session, models, force=True)
        print(f"Inserted {rows} demo sample requests.")
    finally:
        await engine.dispose()


async def _purge_demo() -> None:
    engine = create_engine(get_settings())
    try:
        async with create_session_factory(engine)() as session:
            await purge_demo_data(session)
        print("Removed demo models and demo requests.")
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=["reseed-demo", "purge-demo"])
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level, "text")
    asyncio.run(_reseed_demo() if args.command == "reseed-demo" else _purge_demo())


if __name__ == "__main__":
    main()
