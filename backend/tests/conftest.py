"""Test fixtures.

Tests run against a real PostgreSQL database (analytics rely on percentile_cont and FILTER),
migrated with Alembic so the migrations themselves are exercised. Outbound HTTP from the
inference providers goes to an in-process fake instead of the network.

By default the suite uses an `observatory_test` database on the same server and with the same
credentials as local development, and creates it on first run. Set TEST_DATABASE_URL to use another
one. Its name must contain "test", because every run drops all of its tables.
"""

import os
import re
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

from alembic import command
from app.config import Settings
from app.db.connectivity import database_unavailable_message
from app.main import create_app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://observatory:observatory@localhost:5432/observatory_test"
)
BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_SECRET_KEY = "test-secret-key-0123456789-abcdefghijklmnop"

Handler = httpx.Response | Callable[[httpx.Request], httpx.Response]


class FakeUpstream:
    """Stands in for inference endpoints. Register a response (or a function) per method+URL;
    anything unregistered returns 404. Every request is kept for assertions."""

    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], Handler] = {}
        self.requests: list[httpx.Request] = []

    def on(self, method: str, url: str, handler: Handler) -> None:
        self._handlers[(method.upper(), url)] = handler

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        handler = self._handlers.get((request.method, str(request.url)))
        if handler is None:
            return httpx.Response(404, json={"error": "not registered in FakeUpstream"})
        return handler(request) if callable(handler) else handler

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)


def alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.attributes["database_url"] = database_url
    return config


def ensure_test_database(url: str) -> None:
    """Create the test database if it is missing. Stops the run with a readable message on failure."""
    target = make_url(url)
    name = target.database or ""
    if "test" not in name or not re.fullmatch(r"[A-Za-z0-9_]+", name):
        pytest.exit(
            f'TEST_DATABASE_URL must name a dedicated test database (got "{name}"): the suite drops every table in it.',
            returncode=2,
        )

    # Connect to the server's maintenance database to check for (and create) the test database.
    engine = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        try:
            connection = engine.connect()
        except DBAPIError as exc:
            pytest.exit(database_unavailable_message(url, exc), returncode=2)
        with connection:
            if connection.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}):
                return
            try:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
            except DBAPIError as exc:
                reason = str(exc.orig).strip().splitlines()[0]
                pytest.exit(
                    f'Could not create the test database "{name}": {reason}. '
                    "Create it yourself, or give the role CREATEDB.",
                    returncode=2,
                )
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def database_url() -> str:
    ensure_test_database(TEST_DATABASE_URL)
    config = alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return TEST_DATABASE_URL


@pytest.fixture
def clean_database(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE registered_models, inference_requests, request_metrics, health_checks "
                "RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        secret_key=TEST_SECRET_KEY,
        demo_mode=False,
        demo_simulate_latency=False,
        health_check_interval_seconds=0,
        log_level="WARNING",
        log_format="text",
    )


@pytest.fixture
def upstream() -> FakeUpstream:
    return FakeUpstream()


@pytest.fixture
async def app(settings: Settings, upstream: FakeUpstream, clean_database: None):
    application = create_app(settings, http_transport=upstream.transport)
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
async def session(app) -> AsyncIterator[AsyncSession]:
    async with app.state.session_factory() as db_session:
        yield db_session


async def register_model(client: httpx.AsyncClient, **overrides) -> dict:
    payload = {"name": "demo-model", "provider": "demo", "model_identifier": "orbit-8b"} | overrides
    response = await client.post("/api/models", json=payload)
    assert response.status_code == 201, response.text
    return response.json()
