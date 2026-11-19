"""Hugging Face text-generation endpoints.

Works with Inference Endpoints / self-hosted Text Generation Inference (TGI) and with the
classic serverless Inference API (https://api-inference.huggingface.co/models/<id>). Both accept
the `{"inputs": ..., "parameters": {...}}` payload. For HF's OpenAI-compatible router, register
the model with the "openai_compatible" provider instead.
"""

from typing import Any

import httpx

from app.models.enums import ProviderKind
from app.providers.base import (
    CompletionRequest,
    CompletionResult,
    EndpointConfig,
    InferenceProvider,
    ProviderError,
    ProviderErrorKind,
    estimated_usage,
    require_endpoint_url,
)
from app.providers.http import auth_headers, join_url, parse_json, send_request

HEALTH_CHECK_TIMEOUT_SECONDS = 10.0


class HuggingFaceProvider(InferenceProvider):
    kind = ProviderKind.HUGGINGFACE

    def __init__(self, http_client: httpx.AsyncClient):
        self._client = http_client

    async def complete(self, endpoint: EndpointConfig, request: CompletionRequest) -> CompletionResult:
        response = await send_request(
            self._client,
            "POST",
            require_endpoint_url(endpoint),
            json={"inputs": _build_prompt(request), "parameters": _build_parameters(request)},
            headers=auth_headers(endpoint.api_key),
            timeout=endpoint.timeout_seconds,
        )
        text = _extract_generated_text(parse_json(response))
        # TGI reports generated token counts but not prompt tokens, so the totals stay
        # marked as estimated rather than mixing exact and estimated numbers.
        return CompletionResult(
            text=text,
            usage=estimated_usage(request, text),
            upstream_status_code=response.status_code,
        )

    async def check_health(self, endpoint: EndpointConfig) -> None:
        base_url = require_endpoint_url(endpoint)
        timeout = min(endpoint.timeout_seconds, HEALTH_CHECK_TIMEOUT_SECONDS)
        headers = auth_headers(endpoint.api_key)
        try:
            # TGI and Inference Endpoints expose /health.
            await send_request(self._client, "GET", join_url(base_url, "health"), headers=headers, timeout=timeout)
        except ProviderError as error:
            if error.status_code not in (404, 405):
                raise
            # The serverless API has no /health route, but GET on the model URL returns its status.
            await send_request(self._client, "GET", base_url, headers=headers, timeout=timeout)


def _build_prompt(request: CompletionRequest) -> str:
    if request.system_prompt:
        return f"{request.system_prompt}\n\n{request.prompt}"
    return request.prompt


def _build_parameters(request: CompletionRequest) -> dict[str, Any]:
    parameters: dict[str, Any] = {"max_new_tokens": request.max_tokens, "return_full_text": False}
    # TGI rejects temperature=0; greedy decoding is requested with do_sample=false instead.
    if request.temperature > 0:
        parameters.update(temperature=request.temperature, do_sample=True)
    else:
        parameters["do_sample"] = False
    return parameters


def _extract_generated_text(body: Any) -> str:
    item = body[0] if isinstance(body, list) and body else body
    text = item.get("generated_text") if isinstance(item, dict) else None
    if not isinstance(text, str):
        raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "Response has no generated_text field")
    return text
