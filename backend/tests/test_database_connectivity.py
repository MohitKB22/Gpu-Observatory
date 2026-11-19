"""A missing or misconfigured database must produce one clear sentence, not a driver traceback."""

import pytest
from sqlalchemy.exc import OperationalError

from alembic import command
from app.db.connectivity import DatabaseUnavailableError, database_unavailable_message, describe_database
from app.main import create_app
from tests.conftest import alembic_config

# Port 1 is never a PostgreSQL server, so connecting is refused immediately.
UNREACHABLE_URL = "postgresql+psycopg://observatory:s3cret@127.0.0.1:1/observatory"


def driver_error(detail: str) -> OperationalError:
    return OperationalError("connect", {}, Exception(detail))


def test_description_never_includes_the_password():
    assert describe_database(UNREACHABLE_URL) == "127.0.0.1:1/observatory"
    message = database_unavailable_message(UNREACHABLE_URL, driver_error("Connection refused"))
    assert "s3cret" not in message
    assert "DATABASE_URL" in message


@pytest.mark.parametrize(
    ("detail", "expected"),
    [
        ('connection to server at "::1", port 5432 failed: Connection refused', "connection refused"),
        ('FATAL:  password authentication failed for user "observatory"', "password authentication failed"),
        ('FATAL:  database "observatory" does not exist', 'database "observatory" does not exist'),
        ('FATAL:  role "observatory" does not exist', 'role "observatory" does not exist'),
        ("connection timeout expired", "timed out"),
    ],
)
def test_failure_reason_is_specific(detail, expected):
    assert expected in database_unavailable_message(UNREACHABLE_URL, driver_error(detail))


async def test_startup_stops_with_a_clear_error_when_the_database_is_down(settings):
    app = create_app(settings.model_copy(update={"database_url": UNREACHABLE_URL}))

    with pytest.raises(DatabaseUnavailableError, match="127.0.0.1:1/observatory: connection refused"):
        async with app.router.lifespan_context(app):
            pass


def test_migrations_exit_with_a_clear_error_when_the_database_is_down():
    with pytest.raises(SystemExit) as exit_info:
        command.upgrade(alembic_config(UNREACHABLE_URL), "head")

    assert str(exit_info.value).startswith("Cannot connect to PostgreSQL at 127.0.0.1:1/observatory")


def test_migrations_exit_with_a_clear_error_when_the_url_is_malformed():
    with pytest.raises(SystemExit) as exit_info:
        command.upgrade(alembic_config("not a url s3cret"), "head")

    message = str(exit_info.value)
    assert message.startswith("DATABASE_URL is not a valid database URL")
    assert "s3cret" not in message
