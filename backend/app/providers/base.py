"""Provider interface shared by every inference backend."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

from app.models.enums import ProviderKind, TokenCountSource
from app.utils.tokens import estimate_tokens


@dataclass(frozen=True)
class EndpointConfig:
    provider: ProviderKind
    model_identifier: str
    endpoint_url: str | None
    api_key: str | None
    timeout_seconds: float


@dataclass(frozen=True)
class CompletionRequest:
    prompt: str
    system_prompt: str | None
    temperature: float
    max_tokens: int


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    source: TokenCountSource

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class CompletionResult:
    text: str
    usage: TokenUsage
    upstream_status_code: int | None = None


class ProviderErrorKind(StrEnum):
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    AUTH = "auth"
    HTTP = "http"
    INVALID_RESPONSE = "invalid_response"
    CONFIGURATION = "configuration"


class ProviderError(Exception):
    def __init__(self, kind: ProviderErrorKind, message: str, status_code: int | None = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.status_code = status_code


class InferenceProvider(ABC):
    kind: ProviderKind

    @abstractmethod
    async def complete(self, endpoint: EndpointConfig, request: CompletionRequest) -> CompletionResult:
        """Run one completion. Raises ProviderError on any failure."""

    @abstractmethod
    async def check_health(self, endpoint: EndpointConfig) -> None:
        """Probe the endpoint. Returns normally when reachable, raises ProviderError otherwise."""


def estimated_usage(request: CompletionRequest, completion_text: str) -> TokenUsage:
    prompt_text = f"{request.system_prompt}\n{request.prompt}" if request.system_prompt else request.prompt
    return TokenUsage(
        prompt_tokens=estimate_tokens(prompt_text),
        completion_tokens=estimate_tokens(completion_text),
        source=TokenCountSource.ESTIMATED,
    )


def require_endpoint_url(endpoint: EndpointConfig) -> str:
    if not endpoint.endpoint_url:
        raise ProviderError(ProviderErrorKind.CONFIGURATION, "This model has no endpoint URL configured")
    return endpoint.endpoint_url
