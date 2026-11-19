from fastapi import APIRouter

from app.api.deps import ProvidersDep, SecretBoxDep, SessionDep
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
    payload: InferenceCreate, session: SessionDep, providers: ProvidersDep, secret_box: SecretBoxDep
):
    """Run a completion against a registered model and record it.

    Upstream failures (timeouts, HTTP errors, bad responses) are recorded and returned with
    `status: "error"` and HTTP 200, because the attempt itself was executed and logged.
    Requests that never reach the provider (unknown or disabled model, invalid input) return 4xx.
    """
    model = await model_service.get_model(session, payload.model_id)
    return await inference_service.run_inference(session, model, payload, providers, secret_box, payload.source)
