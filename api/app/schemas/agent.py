"""AI agent (NVIDIA Performance Copilot) schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=8000)


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    range: str = Field(default="1h", max_length=16)
    entity_type: str | None = Field(default=None, pattern="^(gpu|deployment|host)$")
    entity_id: str | None = Field(default=None, max_length=36)


class ToolCallRecord(BaseModel):
    """Every tool call is surfaced so answers are auditable, not asserted."""

    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True
    duration_ms: float | None = None
    summary: str | None = None
    error: str | None = None


class AgentChatResponse(BaseModel):
    answer: str
    engine: str = Field(description="rules | llm | hybrid")
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    citations: list[str] = Field(
        default_factory=list,
        description="Tool results the answer is grounded in.",
    )
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    data_source: str = "production"
    refused: bool = False
    refusal_reason: str | None = None
    generated_at: datetime


class AgentToolInfo(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True


class AgentCapabilities(BaseModel):
    llm_enabled: bool
    provider: str
    model: str | None = None
    tools: list[AgentToolInfo]
    max_tool_iterations: int
    fallback_engine: str = "rules"
