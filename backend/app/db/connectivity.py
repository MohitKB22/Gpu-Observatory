"""Turn "can't reach the database" into one actionable sentence instead of a driver traceback."""

import re

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

SETUP_HINT = "Start PostgreSQL or set DATABASE_URL (see README.md, 'Local development')."


class DatabaseUnavailableError(RuntimeError):
    """Raised at startup when the configured database cannot be reached."""


def describe_database(url: str) -> str:
    """host:port/database for messages; the password is never included."""
    parsed = make_url(url)
    return f"{parsed.host or 'localhost'}:{parsed.port or 5432}/{parsed.database or ''}"


def database_unavailable_message(url: str, error: BaseException) -> str:
    return f"Cannot connect to PostgreSQL at {describe_database(url)}: {_failure_reason(error)}. {SETUP_HINT}"


async def check_database_connection(engine: AsyncEngine, url: str) -> None:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except (DBAPIError, OSError) as exc:
        # `from None`: the driver's own traceback adds nothing to the message above.
        raise DatabaseUnavailableError(database_unavailable_message(url, exc)) from None


def _failure_reason(error: BaseException) -> str:
    detail = str(getattr(error, "orig", None) or error)
    lowered = detail.lower()
    if "refused" in lowered:
        return "connection refused (is the server running and listening on that port?)"
    if "password authentication failed" in lowered:
        return "password authentication failed (check the user and password in DATABASE_URL)"
    missing = re.search(r'(role|database) "[^"]+" does not exist', detail)
    if missing:
        return f"{missing.group(0)} (create it, or point DATABASE_URL at an existing one)"
    if "timeout" in lowered or "timed out" in lowered:
        return "the connection timed out (check the host and any firewall)"
    if "could not translate host name" in lowered or "name or service not known" in lowered:
        return "the host name could not be resolved"
    first_line = detail.strip().splitlines()[0] if detail.strip() else type(error).__name__
    return first_line[:200]
