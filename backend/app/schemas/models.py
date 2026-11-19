import uuid
from datetime import datetime
from typing import Annotated
from urllib.parse import urlparse

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, SecretStr, StringConstraints, model_validator

from app.models.enums import ProviderKind


def _validate_endpoint_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("must be an absolute http:// or https:// URL")
    if parsed.username or parsed.password:
        raise ValueError("must not contain credentials; use the API key field instead")
    return value.rstrip("/")


ModelName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
ModelIdentifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
EndpointUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(_validate_endpoint_url)
]
ApiKey = Annotated[SecretStr, Field(max_length=1000)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]
TimeoutSeconds = Annotated[float, Field(ge=1, le=600)]


class ModelCreate(BaseModel):
    name: ModelName
    provider: ProviderKind
    model_identifier: ModelIdentifier
    endpoint_url: EndpointUrl | None = None
    api_key: ApiKey | None = None
    timeout_seconds: TimeoutSeconds = 60
    description: Description | None = None
    is_enabled: bool = True

    @model_validator(mode="after")
    def remote_providers_need_an_endpoint(self) -> "ModelCreate":
        if self.provider != ProviderKind.DEMO and not self.endpoint_url:
            raise ValueError(f"endpoint_url is required for the {self.provider.value} provider")
        return self


class ModelUpdate(BaseModel):
    """Partial update. Omitted fields are unchanged; `api_key` replaces the stored key and
    `clear_api_key` removes it. Sending endpoint_url=null clears the URL."""

    name: ModelName | None = None
    provider: ProviderKind | None = None
    model_identifier: ModelIdentifier | None = None
    endpoint_url: EndpointUrl | None = None
    api_key: ApiKey | None = None
    clear_api_key: bool = False
    timeout_seconds: TimeoutSeconds | None = None
    description: Description | None = None
    is_enabled: bool | None = None

    @model_validator(mode="after")
    def required_fields_cannot_be_null(self) -> "ModelUpdate":
        for field in ("name", "provider", "model_identifier", "timeout_seconds", "is_enabled"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    provider: ProviderKind
    model_identifier: str
    endpoint_url: str | None
    has_api_key: bool
    timeout_seconds: float
    description: str | None
    is_enabled: bool
    is_demo: bool
    status: str
    last_checked_at: datetime | None
    last_check_latency_ms: float | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class HealthCheckRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    checked_at: datetime
    status: str
    latency_ms: float | None
    error_kind: str | None
    error_message: str | None


class ConnectionCheckResponse(BaseModel):
    check: HealthCheckRead
    model: ModelRead
