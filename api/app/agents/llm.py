"""LLM provider abstraction.

The agent must work with no LLM configured at all, so the default provider is
a null implementation and every call site treats the LLM as optional
enrichment over deterministic results.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMMessage:
    role: str  # system | user | assistant | tool
    content: str
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class LLMToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str | None = None
    tool_calls: list[LLMToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    model: str | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


class LLMProvider(ABC):
    name: str = "abstract"
    supports_tools: bool = False

    @abstractmethod
    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 1200,
    ) -> LLMResponse: ...

    @property
    def available(self) -> bool:
        return False


class NullProvider(LLMProvider):
    """Used when no provider is configured. Always declines, never fabricates."""

    name = "none"
    supports_tools = False

    async def complete(
        self, messages, *, tools=None, temperature=0.1, max_tokens=1200
    ) -> LLMResponse:
        return LLMResponse(
            content=None,
            error="no_llm_provider_configured",
            finish_reason="unavailable",
        )

    @property
    def available(self) -> bool:
        return False


class OpenAICompatibleProvider(LLMProvider):
    """Works with the OpenAI Chat Completions API and compatible gateways."""

    name = "openai"
    supports_tools = True

    def __init__(self, api_key: str, model: str, base_url: str = "") -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def complete(
        self, messages, *, tools=None, temperature=0.1, max_tokens=1200
    ) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [self._encode(m) for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{self._base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("llm_http_error", status=exc.response.status_code)
            return LLMResponse(error=f"llm_http_{exc.response.status_code}")
        except Exception as exc:
            logger.warning("llm_request_failed", error=str(exc)[:200])
            return LLMResponse(error="llm_request_failed")

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        calls = [
            LLMToolCall(
                id=call.get("id", ""),
                name=call.get("function", {}).get("name", ""),
                arguments=_safe_json(call.get("function", {}).get("arguments", "{}")),
            )
            for call in (message.get("tool_calls") or [])
        ]
        return LLMResponse(
            content=message.get("content"),
            tool_calls=calls,
            finish_reason=choice.get("finish_reason"),
            model=data.get("model"),
        )

    @staticmethod
    def _encode(message: LLMMessage) -> dict[str, Any]:
        encoded: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.role == "tool":
            encoded["tool_call_id"] = message.tool_call_id or ""
            if message.name:
                encoded["name"] = message.name
        return encoded


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API with tool use."""

    name = "anthropic"
    supports_tools = True

    def __init__(self, api_key: str, model: str, base_url: str = "") -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or "https://api.anthropic.com/v1").rstrip("/")

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    async def complete(
        self, messages, *, tools=None, temperature=0.1, max_tokens=1200
    ) -> LLMResponse:
        system_prompt = "\n\n".join(m.content for m in messages if m.role == "system")
        converted: list[dict[str, Any]] = []
        for message in messages:
            if message.role == "system":
                continue
            if message.role == "tool":
                converted.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.tool_call_id or "",
                                "content": message.content,
                            }
                        ],
                    }
                )
            else:
                converted.append({"role": message.role, "content": message.content})

        payload: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": converted,
        }
        if system_prompt:
            payload["system"] = system_prompt
        if tools:
            payload["tools"] = [
                {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
                }
                for t in tools
            ]

        try:
            async with httpx.AsyncClient(timeout=settings.LLM_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{self._base_url}/messages",
                    headers={
                        "x-api-key": self._api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("llm_http_error", status=exc.response.status_code)
            return LLMResponse(error=f"llm_http_{exc.response.status_code}")
        except Exception as exc:
            logger.warning("llm_request_failed", error=str(exc)[:200])
            return LLMResponse(error="llm_request_failed")

        text_parts: list[str] = []
        calls: list[LLMToolCall] = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                calls.append(
                    LLMToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input") or {},
                    )
                )
        return LLMResponse(
            content="\n".join(text_parts).strip() or None,
            tool_calls=calls,
            finish_reason=data.get("stop_reason"),
            model=data.get("model"),
        )


class OllamaProvider(OpenAICompatibleProvider):
    """Local Ollama through its OpenAI-compatible endpoint. No key required."""

    name = "ollama"

    def __init__(self, model: str, base_url: str = "") -> None:
        super().__init__(
            api_key="ollama", model=model, base_url=base_url or "http://localhost:11434/v1"
        )

    @property
    def available(self) -> bool:
        return True


def _safe_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def build_provider() -> LLMProvider:
    """Instantiate the configured provider, defaulting to the null provider."""
    provider = settings.LLM_PROVIDER
    if provider == "openai" and settings.LLM_API_KEY:
        return OpenAICompatibleProvider(
            settings.LLM_API_KEY, settings.LLM_MODEL, settings.LLM_BASE_URL
        )
    if provider == "anthropic" and settings.LLM_API_KEY:
        return AnthropicProvider(settings.LLM_API_KEY, settings.LLM_MODEL, settings.LLM_BASE_URL)
    if provider == "ollama":
        return OllamaProvider(settings.LLM_MODEL, settings.LLM_BASE_URL)
    if provider != "none":
        logger.warning(
            "llm_provider_unavailable",
            provider=provider,
            reason="LLM_API_KEY is not set; falling back to deterministic diagnostics",
        )
    return NullProvider()
