import httpx

from app.models.enums import ProviderKind
from app.providers.base import InferenceProvider
from app.providers.demo import DemoProvider
from app.providers.huggingface import HuggingFaceProvider
from app.providers.openai_compatible import OpenAICompatibleProvider
from app.providers.vllm import VLLMProvider


class ProviderRegistry:
    def __init__(self, http_client: httpx.AsyncClient, simulate_demo_latency: bool = True):
        providers: list[InferenceProvider] = [
            DemoProvider(simulate_latency=simulate_demo_latency),
            OpenAICompatibleProvider(http_client),
            VLLMProvider(http_client),
            HuggingFaceProvider(http_client),
        ]
        self._providers = {provider.kind: provider for provider in providers}

    def get(self, kind: str) -> InferenceProvider:
        return self._providers[ProviderKind(kind)]
