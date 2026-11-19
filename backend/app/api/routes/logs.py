import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import SessionDep
from app.schemas.common import DataSource, ErrorResponse, Page, TimeWindow
from app.schemas.inference import InferenceRequestListItem, InferenceRequestRead
from app.services.log_service import LogFilters, get_request, list_requests

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=Page[InferenceRequestListItem])
async def list_logs(
    session: SessionDep,
    search: Annotated[str | None, Query(max_length=200)] = None,
    model_id: uuid.UUID | None = None,
    status: Literal["success", "error"] | None = None,
    source: Literal["playground", "api", "demo_seed"] | None = None,
    # Logs default to everything so recorded demo runs are never hidden; rows carry is_demo.
    data_source: DataSource = DataSource.ALL,
    window: TimeWindow | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
):
    filters = LogFilters(
        search=search or None,
        model_id=model_id,
        status=status,
        source=source,
        data_source=data_source,
        window=window,
    )
    items, total = await list_requests(session, filters, page, page_size)
    return Page[InferenceRequestListItem](items=items, total=total, page=page, page_size=page_size)


@router.get("/{request_id}", response_model=InferenceRequestRead, responses={404: {"model": ErrorResponse}})
async def get_log(request_id: uuid.UUID, session: SessionDep):
    return await get_request(session, request_id)
