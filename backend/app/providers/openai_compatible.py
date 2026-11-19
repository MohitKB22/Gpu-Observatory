"""OpenAI-compatible chat completions (OpenAI, Together, Groq, LM Studio, Ollama, vLLM, ...).

The endpoint URL is the API base including the version prefix, e.g. https://api.openai.com/v1.
"""

from typing import Any

import httpx

from app.models.enums import ProviderKind, TokenCountSource
from app.providers.base import (
    CompletionRequest,
    CompletionResult,
    EndpointConfig,
    InferenceProvider,
    ProviderError,
    ProviderErrorKind,
    TokenUsage,
    estimated_usage,
    require_endpoint_url,
)
from app.providers.http import auth_headers, join_url, parse_json, send_request

HEALTH_CHECK_TIMEOUT_SECONDS = 10.0


class OpenAICompatibleProvider(InferenceProvider):
    kind = ProviderKind.OPENAI_COMPATIBLE

    def __init__(self, http_client: httpx.AsyncClient):
        self._client = http_client

    async def complete(self, endpoint: EndpointConfig, request: CompletionRequest) -> CompletionResult:
        url = join_url(require_endpoint_url(endpoint), "chat/completions")
        payload = {
            "model": endpoint.model_identifier,
            "messages": _build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        response = await send_request(
            self._client,
            "POST",
            url,
            json=payload,
            headers=auth_headers(endpoint.api_key),
            timeout=endpoint.timeout_seconds,
        )
        body = parse_json(response)
        text = _extract_text(body)
        return CompletionResult(
            text=text,
            usage=_extract_usage(body) or estimated_usage(request, text),
            upstream_status_code=response.status_code,
        )

    async def check_health(self, endpoint: EndpointConfig) -> None:
        # GET /models is cheap, needs no tokens, and verifies both reachability and credentials.
        await send_request(
            self._client,
            "GET",
            join_url(require_endpoint_url(endpoint), "models"),
            headers=auth_headers(endpoint.api_key),
            timeout=min(endpoint.timeout_seconds, HEALTH_CHECK_TIMEOUT_SECONDS),
        )


def _build_messages(request: CompletionRequest) -> list[dict[str, str]]:
    messages = []
    if request.system_prompt:
        messages.append({"role": "system", "content": request.system_prompt})
    messages.append({"role": "user", "content": request.prompt})
    return messages


def _extract_text(body: Any) -> str:
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(
            ProviderErrorKind.INVALID_RESPONSE, "Response has no choices[0].message.content field"
        ) from exc
    if content is None:
        return ""
    if not isinstance(content, str):
        raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "Response message content is not text")
    return content


def _extract_usage(body: Any) -> TokenUsage | None:
    usage = body.get("usage") if isinstance(body, dict) else None
    if not isinstance(usage, dict):
        return None
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
        return None
    return TokenUsage(prompt_tokens, completion_tokens, TokenCountSource.EXACT)
