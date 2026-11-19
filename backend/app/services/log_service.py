"""Request history: filtering, search and pagination."""

import contextlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import NotFoundError
from app.models import InferenceRequest, RequestMetrics
from app.schemas.common import DataSource, TimeWindow
from app.schemas.inference import PROMPT_PREVIEW_CHARS, InferenceRequestListItem


@dataclass(frozen=True)
class LogFilters:
    search: str | None = None
    model_id: uuid.UUID | None = None
    status: str | None = None
    source: str | None = None
    data_source: DataSource = DataSource.ALL
    window: TimeWindow | None = None


async def list_requests(
    session: AsyncSession, filters: LogFilters, page: int, page_size: int
) -> tuple[list[InferenceRequestListItem], int]:
    conditions = _conditions(filters)
    total = await session.scalar(select(func.count()).select_from(InferenceRequest).where(*conditions))

    # Select only the columns the table needs; full prompt/response text is loaded per request
    # in the detail view.
    statement = (
        select(
            InferenceRequest.id,
            InferenceRequest.created_at,
            InferenceRequest.model_id,
            InferenceRequest.model_name,
            InferenceRequest.provider,
            InferenceRequest.source,
            InferenceRequest.is_demo,
            InferenceRequest.status,
            func.left(InferenceRequest.prompt, PROMPT_PREVIEW_CHARS).label("prompt_preview"),
            InferenceRequest.error_kind,
            RequestMetrics.latency_ms,
            RequestMetrics.total_tokens,
            RequestMetrics.token_count_source,
            RequestMetrics.tokens_per_second,
        )
        .outerjoin(RequestMetrics, RequestMetrics.request_id == InferenceRequest.id)
        .where(*conditions)
        .order_by(InferenceRequest.created_at.desc(), InferenceRequest.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = await session.execute(statement)
    items = [InferenceRequestListItem.model_validate(row, from_attributes=True) for row in rows]
    return items, total or 0


async def get_request(session: AsyncSession, request_id: uuid.UUID) -> InferenceRequest:
    record = await session.get(InferenceRequest, request_id)
    if record is None:
        raise NotFoundError("Request not found")
    return record


def _conditions(filters: LogFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if filters.model_id is not None:
        conditions.append(InferenceRequest.model_id == filters.model_id)
    if filters.status:
        conditions.append(InferenceRequest.status == filters.status)
    if filters.source:
        conditions.append(InferenceRequest.source == filters.source)
    if filters.data_source == DataSource.REAL:
        conditions.append(InferenceRequest.is_demo.is_(False))
    elif filters.data_source == DataSource.DEMO:
        conditions.append(InferenceRequest.is_demo.is_(True))
    if filters.window is not None:
        conditions.append(InferenceRequest.created_at >= datetime.now(UTC) - filters.window.duration)
    if filters.search:
        conditions.append(_search_condition(filters.search.strip()))
    return conditions


def _search_condition(term: str) -> ColumnElement[bool]:
    pattern = f"%{_escape_like(term)}%"
    matches = [
        InferenceRequest.prompt.ilike(pattern, escape="\\"),
        InferenceRequest.response_text.ilike(pattern, escape="\\"),
        InferenceRequest.error_message.ilike(pattern, escape="\\"),
        InferenceRequest.model_name.ilike(pattern, escape="\\"),
    ]
    with contextlib.suppress(ValueError):
        matches.append(InferenceRequest.id == uuid.UUID(term))
    return or_(*matches)


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
