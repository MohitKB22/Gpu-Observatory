"""HTTP middleware: request IDs, access logs, security headers, rate limiting,
body-size limits and application metrics."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.config import settings
from app.core.errors import error_payload
from app.core.logging import get_logger, request_id_ctx
from app.core.metrics import (
    HTTP_ERRORS,
    HTTP_IN_PROGRESS,
    HTTP_LATENCY,
    HTTP_REQUESTS,
    RATE_LIMIT_REJECTIONS,
)

logger = get_logger(__name__)

# Paths excluded from rate limiting so monitoring never trips the limiter.
_RATE_LIMIT_EXEMPT = {"/health", "/ready", "/live", "/metrics"}


def _route_template(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", None) or request.url.path


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign/propagate a request ID and emit a structured access log."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = (
            incoming if 8 <= len(incoming) <= 64 and incoming.isprintable() else str(uuid.uuid4())
        )
        token = request_id_ctx.set(request_id)
        request.state.request_id = request_id
        started = time.perf_counter()
        HTTP_IN_PROGRESS.inc()
        try:
            response = await call_next(request)
        except Exception:
            duration = time.perf_counter() - started
            path = _route_template(request)
            HTTP_ERRORS.labels(method=request.method, path=path).inc()
            HTTP_LATENCY.labels(method=request.method, path=path).observe(duration)
            logger.exception(
                "request_failed",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration * 1000, 2),
            )
            raise
        finally:
            HTTP_IN_PROGRESS.dec()
            request_id_ctx.reset(token)

        duration = time.perf_counter() - started
        path = _route_template(request)
        HTTP_REQUESTS.labels(
            method=request.method, path=path, status=str(response.status_code)
        ).inc()
        HTTP_LATENCY.labels(method=request.method, path=path).observe(duration)
        if response.status_code >= 500:
            HTTP_ERRORS.labels(method=request.method, path=path).inc()

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-Ms"] = f"{duration * 1000:.2f}"
        if request.url.path not in _RATE_LIMIT_EXEMPT:
            logger.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=round(duration * 1000, 2),
            )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply conservative security headers to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if not settings.SECURE_HEADERS_ENABLED:
            return response
        headers = response.headers
        headers.setdefault("X-Content-Type-Options", "nosniff")
        headers.setdefault("X-Frame-Options", "DENY")
        headers.setdefault("Referrer-Policy", "no-referrer")
        headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        headers.setdefault("Cross-Origin-Resource-Policy", "same-site")
        # The API serves JSON only; a strict CSP is safe here.
        headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
        if settings.ENVIRONMENT == "production":
            headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject oversized request bodies before they are buffered."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if (
            content_length
            and content_length.isdigit()
            and int(content_length) > settings.MAX_REQUEST_BODY_BYTES
        ):
            return JSONResponse(
                status_code=413,
                content=error_payload(
                    "payload_too_large",
                    "Request body exceeds the configured maximum size.",
                    {"max_bytes": settings.MAX_REQUEST_BODY_BYTES},
                ),
            )
        return await call_next(request)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-identity fixed-window rate limiting."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not settings.RATE_LIMIT_ENABLED or request.url.path in _RATE_LIMIT_EXEMPT:
            return await call_next(request)

        from app.core.rate_limit import check_rate_limit

        identity = self._identity(request)
        result = await check_rate_limit(identity)
        if not result.allowed:
            RATE_LIMIT_REJECTIONS.inc()
            logger.warning("rate_limited", identity=identity[:40], path=request.url.path)
            return JSONResponse(
                status_code=429,
                content=error_payload(
                    "rate_limited",
                    "Too many requests. Please retry after the cooldown.",
                    {"retry_after_seconds": result.reset_after},
                ),
                headers={
                    "Retry-After": str(result.reset_after),
                    "X-RateLimit-Limit": str(result.limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        return response

    @staticmethod
    def _identity(request: Request) -> str:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            # Bucket by a short digest of the credential, never the credential.
            import hashlib

            digest = hashlib.sha256(auth[7:].encode()).hexdigest()[:24]
            return f"cred:{digest}"
        client = request.client
        return f"ip:{client.host}" if client else "ip:unknown"


def register_middleware(app: FastAPI) -> None:
    """Register middleware. Starlette runs these in reverse-registration order,
    so the request context (and its request ID) is outermost."""
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
