"""Fixed-window rate limiting backed by the cache abstraction."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app.core.cache import get_cache
from app.core.config import settings


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_after: int


async def check_rate_limit(
    identity: str, *, limit: int | None = None, window: int | None = None
) -> RateLimitResult:
    """Increment the counter for ``identity`` and report whether it may proceed."""
    limit = limit or settings.RATE_LIMIT_REQUESTS
    window = window or settings.RATE_LIMIT_WINDOW_SECONDS
    now = int(time.time())
    bucket = now // window
    key = f"ratelimit:{identity}:{bucket}"

    cache = get_cache()
    try:
        count = await cache.incr(key, window)
    except Exception:
        # A cache outage must not take the API down; fail open but visibly.
        return RateLimitResult(True, limit, limit, window)

    reset_after = ((bucket + 1) * window) - now
    return RateLimitResult(
        allowed=count <= limit,
        limit=limit,
        remaining=max(0, limit - count),
        reset_after=max(1, reset_after),
    )
