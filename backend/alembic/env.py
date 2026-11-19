from logging.config import fileConfig

from sqlalchemy import create_engine, pool
from sqlalchemy.exc import DBAPIError

import app.models  # noqa: F401  (registers tables on Base.metadata)
from alembic import context
from app.config import get_settings
from app.db.base import Base
from app.db.connectivity import database_unavailable_message

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    # Tests pass an explicit URL through the Alembic config; otherwise use DATABASE_URL.
    return config.attributes.get("database_url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # psycopg 3 serves both sync and async, so the same URL works for migrations.
    url = _database_url()
    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        connection = engine.connect()
    except DBAPIError as exc:
        # SystemExit prints just the message and exits with status 1 (the Docker entrypoint retries on that).
        raise SystemExit(database_unavailable_message(url, exc)) from None
    with connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
