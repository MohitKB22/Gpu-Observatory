"""Version 1 API router aggregation."""

from fastapi import APIRouter

from app.api.v1 import analytics, auth, inference, telemetry, websocket, workloads

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(telemetry.router)
api_router.include_router(inference.router)
api_router.include_router(analytics.router)
api_router.include_router(workloads.router)

# The socket lives outside the /api/v1 prefix; see main.py.
websocket_router = websocket.router

__all__ = ["api_router", "websocket_router"]
