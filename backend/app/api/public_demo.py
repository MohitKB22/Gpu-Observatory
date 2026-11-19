"""Restrictions applied when PUBLIC_DEMO=true (an internet-facing demo with no login)."""

import time
from collections import deque
from typing import Annotated

from fastapi import Depends, Request

from app.api.deps import SettingsDep
from app.config import Settings
from app.errors import ForbiddenError, InvalidRequestError, RateLimitedError
from app.models import RegisteredModel
from app.schemas.inference import InferenceCreate

WINDOW_SECONDS = 60.0


class SlidingWindowRateLimiter:
    """In-memory request counter per key over the last minute. Per worker process, which is
    enough to stop casual abuse of a single-instance demo."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str, limit: int) -> bool:
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        if len(self._hits) > 10_000:
            self._forget_idle_keys(now)
        return True

    def _forget_idle_keys(self, now: float) -> None:
        for key in [k for k, hits in self._hits.items() if not hits or now - hits[-1] >= WINDOW_SECONDS]:
            del self._hits[key]


def require_registry_writes(settings: SettingsDep) -> None:
    if settings.public_demo:
        raise ForbiddenError(
            "Registering, editing and deleting models is disabled in this public demo. "
            "Run the project yourself to connect real endpoints."
        )


RegistryWritable = Annotated[None, Depends(require_registry_writes)]


def check_public_demo_inference(
    request: Request, settings: Settings, model: RegisteredModel, payload: InferenceCreate
) -> None:
    if not model.is_demo:
        raise ForbiddenError("Only demo models can be used in this public demo.")
    if len(payload.prompt) > settings.public_demo_max_prompt_chars:
        raise InvalidRequestError(
            f"Prompts are limited to {settings.public_demo_max_prompt_chars:,} characters in this public demo."
        )
    if payload.max_tokens > settings.public_demo_max_tokens:
        raise InvalidRequestError(f"max_tokens is limited to {settings.public_demo_max_tokens} in this public demo.")

    limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
    visitor = request.client.host if request.client else "unknown"
    if not limiter.allow("all", settings.public_demo_global_requests_per_minute) or not limiter.allow(
        f"ip:{visitor}", settings.public_demo_requests_per_minute
    ):
        raise RateLimitedError("Too many demo requests right now. Please wait a minute and try again.")
