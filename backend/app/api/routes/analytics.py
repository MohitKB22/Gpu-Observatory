import uuid

from fastapi import APIRouter

from app.api.deps import DataSourceDep, SamplerDep, SessionDep
from app.schemas.analytics import AnalyticsResponse
from app.schemas.common import TimeWindow
from app.schemas.overview import OverviewResponse
from app.services.analytics_service import build_analytics
from app.services.overview_service import build_overview

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    session: SessionDep, sampler: SamplerDep, data_source: DataSourceDep, window: TimeWindow = TimeWindow.LAST_24_HOURS
):
    return await build_overview(session, window, data_source, sampler)


@router.get("/analytics", response_model=AnalyticsResponse)
async def analytics(
    session: SessionDep,
    data_source: DataSourceDep,
    window: TimeWindow = TimeWindow.LAST_24_HOURS,
    model_id: uuid.UUID | None = None,
):
    return await build_analytics(session, window, data_source, model_id)
