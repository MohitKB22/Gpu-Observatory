"""vLLM serves the OpenAI chat completions API, so inference reuses that provider.

It is a separate provider kind so the UI can label it and so the Infrastructure page knows it
can scrape vLLM's Prometheus `/metrics` endpoint (see app/monitoring/vllm_metrics.py).
"""

from app.models.enums import ProviderKind
from app.providers.openai_compatible import OpenAICompatibleProvider


class VLLMProvider(OpenAICompatibleProvider):
    kind = ProviderKind.VLLM


def server_root_url(endpoint_url: str) -> str:
    """vLLM's API base is usually http://host:8000/v1, while /metrics lives at the server root."""
    url = endpoint_url.rstrip("/")
    return url[: -len("/v1")] if url.endswith("/v1") else url
