from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

import app.models  # noqa: F401
from app.db.base import Base


def test_migrations_match_orm_models(database_url):
    """Fails if a model changes without a matching Alembic migration."""
    engine = create_engine(database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        differences = compare_metadata(context, Base.metadata)
    engine.dispose()

    assert differences == []
