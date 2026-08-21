"""WebSocket connection management and live telemetry broadcast.

Clients that cannot hold a socket open fall back to polling the same REST
endpoints; nothing here is required for the dashboard to function.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket

from app.core.logging import get_logger
from app.core.metrics import WS_CONNECTIONS, WS_MESSAGES

logger = get_logger(__name__)

CHANNELS = {"telemetry", "alerts", "diagnostics"}
MAX_CONNECTIONS = 200


@dataclass
class Connection:
    socket: WebSocket
    channels: set[str] = field(default_factory=lambda: {"telemetry"})
    data_source: str = "production"
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[int, Connection] = {}
        self._lock = asyncio.Lock()

    @property
    def count(self) -> int:
        return len(self._connections)

    async def connect(
        self, socket: WebSocket, *, channels: set[str] | None = None, data_source: str
    ) -> Connection | None:
        if self.count >= MAX_CONNECTIONS:
            await socket.close(code=1013, reason="Server connection limit reached")
            logger.warning("websocket_rejected", reason="limit_reached", count=self.count)
            return None

        await socket.accept()
        connection = Connection(
            socket=socket,
            channels=(channels or {"telemetry"}) & CHANNELS or {"telemetry"},
            data_source=data_source,
        )
        async with self._lock:
            self._connections[id(socket)] = connection
        WS_CONNECTIONS.set(self.count)
        logger.info(
            "websocket_connected",
            total=self.count,
            channels=sorted(connection.channels),
            data_source=data_source,
        )
        return connection

    async def disconnect(self, socket: WebSocket) -> None:
        async with self._lock:
            self._connections.pop(id(socket), None)
        WS_CONNECTIONS.set(self.count)
        logger.info("websocket_disconnected", total=self.count)

    async def send(self, socket: WebSocket, payload: dict[str, Any]) -> bool:
        try:
            await socket.send_text(json.dumps(payload, default=str))
            return True
        except Exception:
            await self.disconnect(socket)
            return False

    async def broadcast(
        self, channel: str, payload: dict[str, Any], *, data_source: str | None = None
    ) -> int:
        """Push to every subscriber of a channel. Returns the delivery count."""
        if not self._connections:
            return 0
        message = json.dumps(
            {
                "channel": channel,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": payload,
            },
            default=str,
        )
        delivered = 0
        stale: list[WebSocket] = []

        for connection in list(self._connections.values()):
            if channel not in connection.channels:
                continue
            if data_source and connection.data_source != data_source:
                continue
            try:
                await connection.socket.send_text(message)
                delivered += 1
            except Exception:
                stale.append(connection.socket)

        for socket in stale:
            await self.disconnect(socket)
        if delivered:
            WS_MESSAGES.labels(channel=channel).inc(delivered)
        return delivered


manager = ConnectionManager()
