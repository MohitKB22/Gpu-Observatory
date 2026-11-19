from fastapi import APIRouter

from app.api.deps import HttpClientDep, SamplerDep, SecretBoxDep, SessionDep, SettingsDep
from app.schemas.infrastructure import InfrastructureResponse, UsageHistoryResponse
from app.services.infrastructure_service import build_infrastructure, build_usage_history

router = APIRouter(prefix="/api/infrastructure", tags=["infrastructure"])


@router.get("", response_model=InfrastructureResponse)
async def infrastructure(
    session: SessionDep,
    sampler: SamplerDep,
    settings: SettingsDep,
    http_client: HttpClientDep,
    secret_box: SecretBoxDep,
):
    return await build_infrastructure(session, sampler, settings, http_client, secret_box)


@router.get("/history", response_model=UsageHistoryResponse)
async def usage_history(sampler: SamplerDep, settings: SettingsDep):
    """In-memory samples from this worker since it started (up to SYSTEM_HISTORY_SIZE)."""
    return build_usage_history(sampler, settings.system_sample_interval_seconds)
