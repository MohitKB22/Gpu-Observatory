"""WebSocket endpoint for live telemetry.

Authentication uses a query-string token because browsers cannot set headers
on a WebSocket handshake. Clients that cannot hold a socket open should poll
the equivalent REST endpoints instead -- the UI degrades to polling
automatically.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.rbac import scopes_for_role
from app.core.security import decode_token, hash_api_key
from app.db.session import get_sessionmaker
from app.models.auth import ApiKey, User
from app.models.enums import DataSource, Scope
from app.realtime.manager import CHANNELS, manager
from app.services import alert_service, telemetry_service

logger = get_logger(__name__)

router = APIRouter(tags=["realtime"])

HEARTBEAT_SECONDS = 25
PUSH_SECONDS = 5


async def _authorize(token: str | None) -> tuple[bool, str]:
    """Validate the handshake credential. Returns (allowed, label)."""
    if not settings.AUTH_ENABLED:
        return True, "auth-disabled"
    if not token:
        return False, "missing_token"

    maker = get_sessionmaker()
    async with maker() as session:
        if token.startswith(f"{settings.API_KEY_PREFIX}_"):
            api_key = await session.scalar(
                select(ApiKey).where(ApiKey.key_hash == hash_api_key(token))
            )
            if api_key is None or not api_key.is_active:
                return False, "invalid_api_key"
            scopes = set(api_key.scope_list)
            if Scope.TELEMETRY_READ.value not in scopes and Scope.ADMIN.value not in scopes:
                return False, "insufficient_scope"
            return True, api_key.name

        try:
            payload = decode_token(token, expected_type="access")
        except Exception:
            return False, "invalid_token"
        user = await session.scalar(select(User).where(User.id == payload.get("sub")))
        if user is None or not user.is_active:
            return False, "inactive_user"
        if Scope.TELEMETRY_READ.value not in scopes_for_role(user.role):
            return False, "insufficient_scope"
        return True, user.email


@router.websocket("/ws/telemetry")
async def telemetry_socket(
    websocket: WebSocket,
    token: str | None = Query(default=None, description="JWT access token or API key."),
    channels: str = Query(default="telemetry", description="Comma-separated channels."),
    source: str | None = Query(default=None, pattern="^(production|demo)$"),
) -> None:
    allowed, label = await _authorize(token)
    if not allowed:
        await websocket.close(code=4401, reason=f"Unauthorized: {label}")
        return

    requested = {c.strip() for c in channels.split(",") if c.strip()} & CHANNELS
    data_source = source or (
        DataSource.DEMO.value if settings.DEMO_MODE else DataSource.PRODUCTION.value
    )

    connection = await manager.connect(
        websocket, channels=requested or {"telemetry"}, data_source=data_source
    )
    if connection is None:
        return

    await manager.send(
        websocket,
        {
            "channel": "system",
            "data": {
                "event": "connected",
                "principal": label,
                "channels": sorted(connection.channels),
                "data_source": data_source,
                "push_interval_seconds": PUSH_SECONDS,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    pusher = asyncio.create_task(_push_loop(websocket, data_source))
    try:
        while True:
            # Client messages are limited to control commands.
            message = await asyncio.wait_for(
                websocket.receive_text(), timeout=HEARTBEAT_SECONDS * 3
            )
            if message == "ping":
                await manager.send(
                    websocket,
                    {
                        "channel": "system",
                        "data": {"event": "pong"},
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception as exc:
        logger.info("websocket_closed", reason=str(exc)[:120])
    finally:
        pusher.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await pusher
        await manager.disconnect(websocket)


async def _push_loop(websocket: WebSocket, data_source: str) -> None:
    """Push a periodic snapshot so clients see movement even between events."""
    maker = get_sessionmaker()
    while True:
        await asyncio.sleep(PUSH_SECONDS)
        try:
            async with maker() as session:
                gpus = await telemetry_service.list_gpus(session, data_source=data_source)
                samples = []
                for gpu in gpus[:8]:
                    latest = await telemetry_service.latest_gpu_metric(
                        session, gpu.id, data_source=data_source
                    )
                    if latest is None:
                        continue
                    samples.append(
                        {
                            "gpu_id": gpu.id,
                            "index": gpu.index,
                            "name": gpu.name,
                            "utilization_pct": latest.utilization_pct,
                            "memory_utilization_pct": latest.memory_utilization_pct,
                            "temperature_c": latest.temperature_c,
                            "power_w": latest.power_w,
                            "recorded_at": latest.recorded_at.isoformat(),
                        }
                    )
                system = await telemetry_service.latest_system_metric(
                    session, data_source=data_source
                )
                freshness = await telemetry_service.telemetry_freshness(
                    session, data_source=data_source
                )
                active_alerts = await alert_service.count_active(session, data_source=data_source)

            ok = await manager.send(
                websocket,
                {
                    "channel": "telemetry",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {
                        "kind": "snapshot",
                        "gpus": samples,
                        "system": {
                            "cpu_utilization_pct": system.cpu_utilization_pct if system else None,
                            "ram_utilization_pct": system.ram_utilization_pct if system else None,
                        },
                        "active_alerts": active_alerts,
                        "freshness": {
                            "age_seconds": freshness.age_seconds,
                            "is_stale": freshness.is_stale,
                        },
                        "data_source": data_source,
                    },
                },
            )
            if not ok:
                return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("websocket_push_failed", error=str(exc)[:160])
