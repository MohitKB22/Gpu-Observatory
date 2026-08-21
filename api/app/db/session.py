"""Async database engine and session management.

PostgreSQL (asyncpg) is the production target. SQLite (aiosqlite) is supported
for local development and the automated test-suite so that the whole stack can
be exercised without external services.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from app.core.config import Settings, settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _engine_kwargs(cfg: Settings) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "echo": cfg.DATABASE_ECHO,
        "future": True,
        "pool_pre_ping": True,
    }
    if cfg.is_sqlite:
        # SQLite has no meaningful server-side pool; NullPool avoids
        # cross-event-loop reuse problems in tests.
        kwargs["poolclass"] = NullPool
        kwargs.pop("pool_pre_ping")
    else:
        kwargs.update(
            pool_size=cfg.DATABASE_POOL_SIZE,
            max_overflow=cfg.DATABASE_MAX_OVERFLOW,
            pool_timeout=cfg.DATABASE_POOL_TIMEOUT,
            pool_recycle=1800,
        )
    return kwargs


def create_engine(cfg: Settings | None = None) -> AsyncEngine:
    cfg = cfg or settings
    return create_async_engine(cfg.DATABASE_URL, **_engine_kwargs(cfg))


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        _engine = create_engine()
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
        logger.info(
            "database_engine_created",
            dialect=_engine.dialect.name,
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


def set_sessionmaker(maker: async_sessionmaker[AsyncSession]) -> None:
    """Override the global sessionmaker (used by tests and background workers)."""
    global _sessionmaker
    _sessionmaker = maker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a transactional session."""
    maker = get_sessionmaker()
    async with maker() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        logger.info("database_engine_disposed")
    _engine = None
    _sessionmaker = None


async def check_database() -> tuple[bool, str]:
    """Lightweight connectivity probe used by /ready."""
    from sqlalchemy import text

    try:
        maker = get_sessionmaker()
        async with maker() as session:
            await session.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # pragma: no cover - failure path
        return False, str(exc)[:200]
