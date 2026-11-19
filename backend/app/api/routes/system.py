from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.api.deps import SessionDep, SettingsDep
from app.schemas.common import DataSource
from app.schemas.system import HealthResponse, SystemInfo

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health", response_model=HealthResponse, responses={503: {"model": HealthResponse}})
async def health(session: SessionDep):
    """Liveness and database connectivity, used by Docker and load balancer health checks."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "degraded", "database": "unreachable"})
    return HealthResponse(status="ok", database="ok")


@router.get("/system/info", response_model=SystemInfo)
async def system_info(settings: SettingsDep) -> SystemInfo:
    return SystemInfo(
        version=__version__,
        environment=settings.app_env,
        demo_mode=settings.demo_mode,
        default_data_source=DataSource.ALL if settings.demo_mode else DataSource.REAL,
    )
