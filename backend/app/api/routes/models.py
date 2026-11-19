import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ProvidersDep, SecretBoxDep, SessionDep
from app.schemas.common import ErrorResponse
from app.schemas.models import ConnectionCheckResponse, HealthCheckRead, ModelCreate, ModelRead, ModelUpdate
from app.services import health_service, model_service

router = APIRouter(prefix="/api/models", tags=["models"], responses={404: {"model": ErrorResponse}})


@router.get("", response_model=list[ModelRead])
async def list_models(session: SessionDep):
    return await model_service.list_models(session)


@router.post(
    "", response_model=ModelRead, status_code=status.HTTP_201_CREATED, responses={409: {"model": ErrorResponse}}
)
async def create_model(payload: ModelCreate, session: SessionDep, secret_box: SecretBoxDep):
    return await model_service.create_model(session, payload, secret_box)


@router.get("/{model_id}", response_model=ModelRead)
async def get_model(model_id: uuid.UUID, session: SessionDep):
    return await model_service.get_model(session, model_id)


@router.patch("/{model_id}", response_model=ModelRead, responses={409: {"model": ErrorResponse}})
async def update_model(model_id: uuid.UUID, payload: ModelUpdate, session: SessionDep, secret_box: SecretBoxDep):
    model = await model_service.get_model(session, model_id)
    return await model_service.update_model(session, model, payload, secret_box)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_model(model_id: uuid.UUID, session: SessionDep) -> Response:
    model = await model_service.get_model(session, model_id)
    await model_service.delete_model(session, model)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{model_id}/check", response_model=ConnectionCheckResponse)
async def check_connection(model_id: uuid.UUID, session: SessionDep, providers: ProvidersDep, secret_box: SecretBoxDep):
    """Probe the endpoint now and record the result. Does not run inference or use tokens."""
    model = await model_service.get_model(session, model_id)
    check = await health_service.run_health_check(session, model, providers, secret_box)
    return ConnectionCheckResponse(check=HealthCheckRead.model_validate(check), model=ModelRead.model_validate(model))


@router.get("/{model_id}/health-checks", response_model=list[HealthCheckRead])
async def list_health_checks(model_id: uuid.UUID, session: SessionDep, limit: Annotated[int, Query(ge=1, le=200)] = 20):
    await model_service.get_model(session, model_id)
    return await health_service.list_health_checks(session, model_id, limit)
