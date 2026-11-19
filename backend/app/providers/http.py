"""HTTP helpers that turn transport and status failures into ProviderError."""

from typing import Any

import httpx

from app.providers.base import ProviderError, ProviderErrorKind

_BODY_EXCERPT_CHARS = 300


def join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def auth_headers(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


async def send_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    timeout: float,
    headers: dict[str, str] | None = None,
    json: Any = None,
) -> httpx.Response:
    try:
        response = await client.request(method, url, json=json, headers=headers, timeout=timeout)
    except httpx.TimeoutException as exc:
        raise ProviderError(ProviderErrorKind.TIMEOUT, f"No response from the endpoint within {timeout:g}s") from exc
    except httpx.RequestError as exc:
        raise ProviderError(
            ProviderErrorKind.CONNECTION, f"Could not reach the endpoint ({type(exc).__name__})"
        ) from exc

    if response.status_code in (401, 403):
        raise ProviderError(
            ProviderErrorKind.AUTH,
            f"Endpoint rejected the credentials (HTTP {response.status_code})",
            status_code=response.status_code,
        )
    if response.status_code >= 400:
        excerpt = response.text[:_BODY_EXCERPT_CHARS].strip()
        detail = f": {excerpt}" if excerpt else ""
        raise ProviderError(
            ProviderErrorKind.HTTP,
            f"Endpoint returned HTTP {response.status_code}{detail}",
            status_code=response.status_code,
        )
    return response


def parse_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError(
            ProviderErrorKind.INVALID_RESPONSE,
            "Endpoint returned a response that is not valid JSON",
            status_code=response.status_code,
        ) from exc
