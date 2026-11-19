from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.api.deps import SessionDep, SettingsDep
from app.schemas.common import DataSource
from app.schemas.inference import MAX_PROMPT_CHARS, MAX_TOKENS
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
        public_demo=settings.public_demo,
        public_demo_source_url=settings.public_demo_source_url or None,
        max_prompt_chars=settings.public_demo_max_prompt_chars if settings.public_demo else MAX_PROMPT_CHARS,
        max_tokens=settings.public_demo_max_tokens if settings.public_demo else MAX_TOKENS,
    )
