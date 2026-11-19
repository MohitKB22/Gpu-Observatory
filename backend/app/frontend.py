"""Serve the built frontend from the API process (single-container deployments such as Render).

docker-compose.yml keeps the separate nginx container; this is only active when STATIC_DIR is set.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.errors import NotFoundError

# Same policy as frontend/nginx/default.conf.template.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'"
    ),
}


class ImmutableStaticFiles(StaticFiles):
    """Vite puts a content hash in every asset name, so assets can be cached forever."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


def mount_frontend(app: FastAPI, directory: str) -> None:
    root = Path(directory).resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"STATIC_DIR={directory} does not contain a built frontend (index.html missing)")

    app.mount("/assets", ImmutableStaticFiles(directory=root / "assets"), name="assets")

    # Registered after every API route, so it only receives paths nothing else matched.
    # HEAD is allowed because hosting probes and uptime monitors check pages with it.
    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def single_page_app(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise NotFoundError("Not found")
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate, headers={"X-Content-Type-Options": "nosniff"})
        # Client-side routes (/models, /logs?request=…) all load the app shell.
        return FileResponse(index, headers={"Cache-Control": "no-cache", **SECURITY_HEADERS})
