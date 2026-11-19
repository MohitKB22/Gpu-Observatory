import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.http")

# Accept a caller-supplied request id only if it is short and plain, so it cannot be used
# to inject content into log lines.
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_QUIET_PATHS = {"/api/health", "/metrics"}


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        incoming_id = request.headers.get("x-request-id", "")
        request_id = incoming_id if _SAFE_REQUEST_ID.match(incoming_id) else uuid.uuid4().hex
        started = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        level = logging.DEBUG if request.url.path in _QUIET_PATHS else logging.INFO
        logger.log(
            level,
            "http request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 1),
            },
        )
        return response
