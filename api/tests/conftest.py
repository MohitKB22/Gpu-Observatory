"""Shared pytest fixtures.

The suite runs against SQLite so the entire stack -- including migrations,
services and the HTTP layer -- is exercised without external dependencies.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("DEMO_MODE", "false")
os.environ.setdefault("TELEMETRY_ENABLED", "false")
os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("RATE_LIMIT_ENABLED", "false")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-any-real-deployment")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.models  # noqa: F401
from app.core.cache import InMemoryCache, set_cache
from app.db.base import Base
from app.db.session import get_session, set_sessionmaker
from app.models.enums import DataSource, UserRole


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def engine():
    """A fresh in-memory database per test."""
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def sessionmaker_fixture(engine) -> async_sessionmaker[AsyncSession]:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    set_sessionmaker(maker)
    set_cache(InMemoryCache())
    return maker


@pytest_asyncio.fixture
async def session(sessionmaker_fixture) -> AsyncGenerator[AsyncSession, None]:
    async with sessionmaker_fixture() as s:
        yield s


@pytest_asyncio.fixture
async def app_instance(sessionmaker_fixture):
    """The FastAPI app with its lifespan bypassed and DB overridden."""
    from app.main import create_app

    application = create_app()
    application.router.lifespan_context = _noop_lifespan

    async def _override() -> AsyncGenerator[AsyncSession, None]:
        async with sessionmaker_fixture() as s:
            yield s

    application.dependency_overrides[get_session] = _override
    return application


def _noop_lifespan(app):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _ctx(_app):
        yield

    return _ctx(app)


@pytest_asyncio.fixture
async def client(app_instance) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app_instance), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_user(session):
    from app.schemas.auth import UserCreate
    from app.services.auth_service import create_user

    return await create_user(
        session,
        UserCreate(
            email="admin@test.local",
            password="test-password-1234",
            full_name="Test Admin",
            role=UserRole.ADMIN.value,
        ),
    )


@pytest_asyncio.fixture
async def viewer_user(session):
    from app.schemas.auth import UserCreate
    from app.services.auth_service import create_user

    return await create_user(
        session,
        UserCreate(
            email="viewer@test.local",
            password="test-password-1234",
            role=UserRole.VIEWER.value,
        ),
    )


@pytest_asyncio.fixture
async def admin_headers(client, admin_user) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.local", "password": "test-password-1234"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def viewer_headers(client, viewer_user) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "viewer@test.local", "password": "test-password-1234"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest_asyncio.fixture
async def seeded_demo(session):
    """40 minutes of demo telemetry in the under-batching scenario."""
    from app.demo.runner import backfill

    await backfill(session, minutes=40, scenario="under_batching", step_seconds=60)
    return DataSource.DEMO.value
