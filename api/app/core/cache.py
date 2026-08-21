"""Cache abstraction with a Redis implementation and an in-memory fallback.

The in-memory backend is intentionally process-local. It exists so the platform
degrades gracefully (and remains testable) when Redis is unreachable -- it is
never presented as a distributed cache.
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class CacheBackend(ABC):
    name: str = "abstract"

    @abstractmethod
    async def get(self, key: str) -> Any | None: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: int | None = None) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def incr(self, key: str, ttl: int) -> int:
        """Increment a counter, setting its TTL on first write. Used by the
        rate limiter."""

    @abstractmethod
    async def ping(self) -> bool: ...

    async def close(self) -> None:  # pragma: no cover - trivial
        return None


class InMemoryCache(CacheBackend):
    name = "memory"

    def __init__(self) -> None:
        self._data: dict[str, tuple[float | None, Any]] = {}
        self._lock = asyncio.Lock()

    def _live(self, key: str) -> Any | None:
        item = self._data.get(key)
        if item is None:
            return None
        expires, value = item
        if expires is not None and expires < time.monotonic():
            self._data.pop(key, None)
            return None
        return value

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            return self._live(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        async with self._lock:
            expires = time.monotonic() + ttl if ttl else None
            self._data[key] = (expires, value)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._data.pop(key, None)

    async def incr(self, key: str, ttl: int) -> int:
        async with self._lock:
            current = self._live(key)
            value = int(current or 0) + 1
            expires = self._data[key][0] if current is not None else time.monotonic() + ttl
            self._data[key] = (expires, value)
            return value

    async def ping(self) -> bool:
        return True

    async def clear(self) -> None:
        async with self._lock:
            self._data.clear()


class RedisCache(CacheBackend):
    name = "redis"

    def __init__(self, url: str) -> None:
        import redis.asyncio as aioredis

        self._client = aioredis.from_url(
            url, encoding="utf-8", decode_responses=True, socket_connect_timeout=2
        )

    async def get(self, key: str) -> Any | None:
        raw = await self._client.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    async def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        payload = json.dumps(value, default=str)
        if ttl:
            await self._client.setex(key, ttl, payload)
        else:
            await self._client.set(key, payload)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def incr(self, key: str, ttl: int) -> int:
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl, nx=True)
        result = await pipe.execute()
        return int(result[0])

    async def ping(self) -> bool:
        try:
            return bool(await self._client.ping())
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()


_cache: CacheBackend | None = None


async def init_cache() -> CacheBackend:
    """Initialise the cache, falling back to memory if Redis is unavailable."""
    global _cache
    if _cache is not None:
        return _cache
    if settings.REDIS_ENABLED:
        try:
            candidate = RedisCache(settings.REDIS_URL)
            if await candidate.ping():
                _cache = candidate
                logger.info("cache_initialised", backend="redis")
                return _cache
            await candidate.close()
            logger.warning("redis_unreachable_falling_back", url_scheme="redis")
        except Exception as exc:
            logger.warning("redis_init_failed_falling_back", error=str(exc)[:200])
    _cache = InMemoryCache()
    logger.info("cache_initialised", backend="memory")
    return _cache


def get_cache() -> CacheBackend:
    global _cache
    if _cache is None:
        _cache = InMemoryCache()
    return _cache


def set_cache(backend: CacheBackend) -> None:
    global _cache
    _cache = backend


async def close_cache() -> None:
    global _cache
    if _cache is not None:
        await _cache.close()
    _cache = None


async def check_cache() -> tuple[bool, str]:
    cache = get_cache()
    ok = await cache.ping()
    return ok, cache.name
