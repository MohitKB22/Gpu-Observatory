from fastapi import APIRouter, Request

from app.api.deps import ProvidersDep, SecretBoxDep, SessionDep, SettingsDep
from app.api.public_demo import check_public_demo_inference
from app.schemas.common import ErrorResponse
from app.schemas.inference import InferenceCreate, InferenceRequestRead
from app.services import inference_service, model_service

router = APIRouter(prefix="/api/inference", tags=["inference"])


@router.post(
    "",
    response_model=InferenceRequestRead,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
async def run_inference(
    request: Request,
    payload: InferenceCreate,
    session: SessionDep,
    providers: ProvidersDep,
    secret_box: SecretBoxDep,
    settings: SettingsDep,
):
    """Run a completion against a registered model and record it.

    Upstream failures (timeouts, HTTP errors, bad responses) are recorded and returned with
    `status: "error"` and HTTP 200, because the attempt itself was executed and logged.
    Requests that never reach the provider (unknown or disabled model, invalid input) return 4xx.
    """
    model = await model_service.get_model(session, payload.model_id)
    if settings.public_demo:
        check_public_demo_inference(request, settings, model, payload)
    record = await inference_service.run_inference(session, model, payload, providers, secret_box, payload.source)
    if settings.public_demo:
        await inference_service.prune_visitor_requests(session, keep=settings.public_demo_kept_requests)
    return record
