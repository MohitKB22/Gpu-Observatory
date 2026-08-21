"""Audit logging helper.

Audit writes use their own session so that a failed business transaction can
still leave an audit trail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.core.logging import get_logger, request_id_ctx
from app.models.auth import AuditLog

logger = get_logger(__name__)


async def record_audit(
    *,
    action: str,
    outcome: str = "success",
    actor_type: str = "system",
    actor_id: str | None = None,
    actor_label: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    source_ip: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Persist an audit entry. Never raises into the caller's request path."""
    from app.db.session import get_sessionmaker

    entry = AuditLog(
        occurred_at=datetime.now(timezone.utc),
        actor_type=actor_type,
        actor_id=actor_id,
        actor_label=actor_label,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        request_id=request_id_ctx.get(),
        source_ip=source_ip,
        detail=json.dumps(detail, default=str) if detail else None,
    )
    try:
        maker = get_sessionmaker()
        async with maker() as session:
            session.add(entry)
            await session.commit()
    except Exception as exc:  # pragma: no cover - audit must not break requests
        logger.warning("audit_write_failed", action=action, error=str(exc)[:200])
    logger.info(
        "audit",
        action=action,
        outcome=outcome,
        actor_type=actor_type,
        actor_label=actor_label,
        resource_type=resource_type,
        resource_id=resource_id,
    )
