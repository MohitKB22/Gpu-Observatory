"""Model registry operations."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ConflictError, InvalidRequestError, NotFoundError
from app.models import RegisteredModel
from app.models.enums import ModelStatus, ProviderKind
from app.providers.base import EndpointConfig, ProviderError, ProviderErrorKind
from app.schemas.models import ModelCreate, ModelUpdate
from app.security import SecretBox, SecretDecryptionError

# Changing any of these makes the previous connection check meaningless.
_CONNECTION_FIELDS = {"provider", "model_identifier", "endpoint_url"}


async def list_models(session: AsyncSession) -> list[RegisteredModel]:
    result = await session.scalars(select(RegisteredModel).order_by(RegisteredModel.created_at))
    return list(result)


async def get_model(session: AsyncSession, model_id: uuid.UUID) -> RegisteredModel:
    model = await session.get(RegisteredModel, model_id)
    if model is None:
        raise NotFoundError("Model not found")
    return model


async def create_model(session: AsyncSession, payload: ModelCreate, secret_box: SecretBox) -> RegisteredModel:
    model = RegisteredModel(
        name=payload.name,
        provider=payload.provider.value,
        model_identifier=payload.model_identifier,
        endpoint_url=payload.endpoint_url,
        timeout_seconds=payload.timeout_seconds,
        description=payload.description,
        is_enabled=payload.is_enabled,
        status=ModelStatus.UNKNOWN.value,
    )
    if payload.api_key and payload.api_key.get_secret_value():
        model.encrypted_api_key = secret_box.encrypt(payload.api_key.get_secret_value())
    session.add(model)
    await _commit_checking_name(session, payload.name)
    return model


async def update_model(
    session: AsyncSession, model: RegisteredModel, payload: ModelUpdate, secret_box: SecretBox
) -> RegisteredModel:
    changes = payload.model_dump(mode="json", exclude_unset=True, exclude={"api_key", "clear_api_key"})

    # Validate the merged result before touching the ORM object.
    provider = changes.get("provider", model.provider)
    endpoint_url = changes.get("endpoint_url", model.endpoint_url)
    if provider != ProviderKind.DEMO and not endpoint_url:
        raise InvalidRequestError(f"endpoint_url is required for the {provider} provider")

    connection_changed = any(
        field in _CONNECTION_FIELDS and getattr(model, field) != value for field, value in changes.items()
    )
    for field, value in changes.items():
        setattr(model, field, value)

    if payload.clear_api_key:
        model.encrypted_api_key = None
        connection_changed = True
    if payload.api_key and payload.api_key.get_secret_value():
        model.encrypted_api_key = secret_box.encrypt(payload.api_key.get_secret_value())
        connection_changed = True

    if connection_changed:
        model.status = ModelStatus.UNKNOWN.value
        model.last_error = None

    await _commit_checking_name(session, model.name)
    return model


async def delete_model(session: AsyncSession, model: RegisteredModel) -> None:
    # Request history keeps the model name (model_id is set to NULL by the FK);
    # health checks are removed with the model.
    await session.delete(model)
    await session.commit()


def build_endpoint_config(model: RegisteredModel, secret_box: SecretBox) -> EndpointConfig:
    api_key = None
    if model.encrypted_api_key:
        try:
            api_key = secret_box.decrypt(model.encrypted_api_key)
        except SecretDecryptionError as exc:
            raise ProviderError(ProviderErrorKind.CONFIGURATION, str(exc)) from exc
    return EndpointConfig(
        provider=ProviderKind(model.provider),
        model_identifier=model.model_identifier,
        endpoint_url=model.endpoint_url,
        api_key=api_key,
        timeout_seconds=model.timeout_seconds,
    )


async def _commit_checking_name(session: AsyncSession, name: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        if "uq_registered_models_name" in str(exc.orig):
            raise ConflictError(f'A model named "{name}" already exists') from exc
        raise
