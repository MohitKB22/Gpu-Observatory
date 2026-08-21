"""NVIDIA Performance Copilot.

Architecture:

* Tools are the only source of numbers. The LLM is never asked to recall or
  estimate a metric; it receives tool output and explains it.
* The deterministic diagnostics engine runs on every request, independent of
  the LLM. If no LLM is configured, or the LLM fails, the agent still answers
  from rules and measured values.
* The LLM's role is narration and synthesis over grounded facts.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents import guard
from app.agents.llm import LLMMessage, LLMProvider, build_provider
from app.agents.tools import TOOL_REGISTRY, ToolContext, invoke, tool_schemas
from app.core.config import settings
from app.core.logging import get_logger
from app.core.metrics import AGENT_ERRORS, AGENT_LATENCY, AGENT_REQUESTS
from app.core.timerange import resolve_range
from app.schemas.agent import (
    AgentCapabilities,
    AgentChatRequest,
    AgentChatResponse,
    AgentToolInfo,
    ToolCallRecord,
)
from app.services.diagnostics import diagnose
from app.services.diagnostics.engine import summarise_for_agent

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are the NVIDIA Performance Copilot, an AI infrastructure \
performance analyst for the NVIDIA AI Performance Observatory.

Absolute rules:
1. NEVER invent, estimate, or recall a metric value. Every number you state must \
come from a tool result in this conversation. If a tool did not return a value, \
say the data is unavailable.
2. Call tools to gather evidence before answering. Prefer several targeted \
tool calls over one broad guess.
3. Distinguish measured values from estimates. Cost figures are always estimates \
derived from a configurable pricing profile -- say so when you cite them.
4. If the evidence does not support a conclusion, say so plainly rather than \
speculating. It is correct and useful to answer "the data does not show that".
5. State a confidence level and the reasoning behind it.
6. You have no ability to run commands, change configuration, or write data. \
Recommendations are advisory only.
7. Be concise and technical. Lead with the answer, then the evidence, then the \
recommendation.

You have been given the output of a deterministic rules engine that has already \
analysed the current window. Treat those findings as authoritative and build on \
them; do not contradict them without tool evidence."""


class PerformanceCopilot:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or build_provider()

    # ------------------------------------------------------------ metadata --
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            llm_enabled=self.provider.available,
            provider=self.provider.name,
            model=settings.LLM_MODEL if self.provider.available else None,
            tools=[
                AgentToolInfo(
                    name=spec.name,
                    description=spec.description,
                    parameters=spec.parameters,
                    read_only=spec.read_only,
                )
                for spec in TOOL_REGISTRY.values()
            ],
            max_tool_iterations=settings.LLM_MAX_TOOL_ITERATIONS,
            fallback_engine="rules",
        )

    # ---------------------------------------------------------------- chat --
    async def chat(
        self, session: AsyncSession, request: AgentChatRequest, *, data_source: str
    ) -> AgentChatResponse:
        started = time.perf_counter()

        verdict = guard.inspect(request.message)
        if not verdict.allowed:
            AGENT_REQUESTS.labels(engine="guard", outcome="refused").inc()
            logger.info("agent_request_refused", category=verdict.category, reason=verdict.reason)
            return AgentChatResponse(
                answer=verdict.message or "That request cannot be processed.",
                engine="guard",
                confidence=1.0,
                data_source=data_source,
                refused=True,
                refusal_reason=verdict.category,
                generated_at=datetime.now(timezone.utc),
            )

        time_range = resolve_range(request.range)
        ctx = ToolContext(
            session=session,
            data_source=data_source,
            default_range=time_range.label if time_range.label != "custom" else "1h",
            entity_type=request.entity_type,
            entity_id=request.entity_id,
        )

        # The rules engine always runs -- it is the grounding layer.
        findings, _diag_ctx = await diagnose(
            session,
            time_range=time_range,
            data_source=data_source,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            persist_results=False,
        )

        records: list[ToolCallRecord] = []
        citations: list[str] = []

        # Always gather a baseline evidence set so an answer exists regardless
        # of whether the LLM is available.
        for tool_name in self._baseline_tools(request.message):
            result, duration = await invoke(tool_name, ctx, {"range": ctx.default_range})
            records.append(
                ToolCallRecord(
                    tool=tool_name,
                    arguments={"range": ctx.default_range},
                    ok=result.ok,
                    duration_ms=round(duration, 2),
                    summary=result.summary,
                    error=result.error,
                )
            )
            if result.ok and result.summary:
                citations.append(f"{tool_name}: {result.summary}")

        if not self.provider.available:
            answer = self._deterministic_answer(request.message, findings, records)
            AGENT_REQUESTS.labels(engine="rules", outcome="ok").inc()
            AGENT_LATENCY.labels(engine="rules").observe(time.perf_counter() - started)
            return AgentChatResponse(
                answer=answer,
                engine="rules",
                tool_calls=records,
                citations=citations,
                confidence=findings[0].confidence if findings else 0.5,
                data_source=data_source,
                generated_at=datetime.now(timezone.utc),
            )

        try:
            answer, llm_records = await self._llm_answer(ctx, request, findings, records, citations)
            records = llm_records
            AGENT_REQUESTS.labels(engine="llm", outcome="ok").inc()
            AGENT_LATENCY.labels(engine="llm").observe(time.perf_counter() - started)
            return AgentChatResponse(
                answer=answer,
                engine="hybrid",
                tool_calls=records,
                citations=citations,
                confidence=findings[0].confidence if findings else 0.6,
                data_source=data_source,
                generated_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.exception("agent_llm_failed", error=str(exc)[:200])
            AGENT_ERRORS.labels(reason="llm_failure").inc()
            AGENT_REQUESTS.labels(engine="llm", outcome="error").inc()
            answer = self._deterministic_answer(request.message, findings, records)
            return AgentChatResponse(
                answer=(
                    answer + "\n\n_(The language model was unavailable, so this answer was "
                    "produced by the deterministic diagnostics engine.)_"
                ),
                engine="rules",
                tool_calls=records,
                citations=citations,
                confidence=findings[0].confidence if findings else 0.5,
                data_source=data_source,
                generated_at=datetime.now(timezone.utc),
            )

    # ----------------------------------------------------------- LLM path ---
    async def _llm_answer(
        self,
        ctx: ToolContext,
        request: AgentChatRequest,
        findings: list[Any],
        records: list[ToolCallRecord],
        citations: list[str],
    ) -> tuple[str, list[ToolCallRecord]]:
        grounding = summarise_for_agent(findings)
        baseline = "\n".join(f"- {r.tool}: {r.summary}" for r in records if r.ok and r.summary)

        messages: list[LLMMessage] = [
            LLMMessage("system", SYSTEM_PROMPT),
            LLMMessage(
                "system",
                (
                    f"Data source: {ctx.data_source}. Analysis window: {ctx.default_range}.\n\n"
                    f"Deterministic rules-engine findings:\n{grounding}\n\n"
                    f"Baseline tool measurements already gathered:\n{baseline or 'none'}"
                ),
            ),
        ]
        for entry in request.history[-8:]:
            messages.append(LLMMessage(entry.role, entry.content))
        messages.append(LLMMessage("user", request.message))

        schemas = tool_schemas()
        for _iteration in range(settings.LLM_MAX_TOOL_ITERATIONS):
            response = await self.provider.complete(messages, tools=schemas)
            if not response.ok:
                raise RuntimeError(response.error or "llm_error")

            if not response.tool_calls:
                return (response.content or "").strip() or self._deterministic_answer(
                    request.message, findings, records
                ), records

            messages.append(
                LLMMessage(
                    "assistant",
                    response.content
                    or f"Calling tools: {', '.join(c.name for c in response.tool_calls)}",
                )
            )

            for call in response.tool_calls:
                result, duration = await invoke(call.name, ctx, call.arguments)
                records.append(
                    ToolCallRecord(
                        tool=call.name,
                        arguments=call.arguments,
                        ok=result.ok,
                        duration_ms=round(duration, 2),
                        summary=result.summary,
                        error=result.error,
                    )
                )
                if result.ok and result.summary:
                    citations.append(f"{call.name}: {result.summary}")
                payload = (
                    json.dumps(result.data, default=str)
                    if result.ok
                    else json.dumps({"error": result.error})
                )
                messages.append(
                    LLMMessage(
                        "tool",
                        guard.sanitize_tool_output(payload),
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )

        # Iteration budget exhausted: ask for a final answer with no more tools.
        final = await self.provider.complete(messages, tools=None)
        if final.ok and final.content:
            return final.content.strip(), records
        return self._deterministic_answer(request.message, findings, records), records

    # -------------------------------------------------------- rules path ----
    @staticmethod
    def _baseline_tools(message: str) -> list[str]:
        """Choose the evidence to gather up front, based on the question."""
        text = message.lower()
        tools = ["get_current_gpu_metrics", "get_inference_metrics"]

        if any(k in text for k in ("batch", "batching", "under-batch", "underbatch")):
            tools.append("get_batch_metrics")
        if any(k in text for k in ("cost", "expensive", "cheap", "spend", "price", "budget")):
            tools.append("get_cost_metrics")
        if any(k in text for k in ("latency", "slow", "p95", "p99", "percentile", "response time")):
            tools.append("get_latency_percentiles")
        if any(k in text for k in ("model", "compare", "fastest", "which", "versus", " vs ")):
            tools.append("get_model_metrics")
        if any(k in text for k in ("alert", "incident", "alarm", "page")):
            tools.append("get_recent_alerts")
        if any(k in text for k in ("cpu", "host", "memory", "ram", "bottleneck")):
            tools.append("get_cpu_metrics")
        if any(k in text for k in ("history", "historical", "previous", "before", "trend", "past")):
            tools.append("query_historical_incidents")

        if len(tools) == 2:  # generic question: widen the evidence net
            tools.extend(["get_batch_metrics", "get_cpu_metrics"])
        # Preserve order, drop duplicates, and bound the number of calls.
        return list(dict.fromkeys(tools))[:6]

    @staticmethod
    def _deterministic_answer(
        message: str, findings: list[Any], records: list[ToolCallRecord]
    ) -> str:
        """Compose an answer from rules output and measured values only."""
        if not findings:
            return (
                "I could not find telemetry for the selected window, so I cannot "
                "answer that from measured data. Confirm a telemetry agent is "
                "reporting, or enable Demo Mode to explore the platform."
            )

        top = findings[0]
        lines: list[str] = []

        if top.kind == "healthy":
            lines.append(
                "**No performance problems are visible in the selected window.** "
                "All monitored signals are within their expected ranges."
            )
        else:
            lines.append(f"**{top.title}**")
            lines.append("")
            lines.append(top.root_cause)

        if top.evidence:
            lines.append("")
            lines.append("**Evidence**")
            for item in top.evidence:
                lines.append(f"- {item}")

        if top.impact:
            lines.append("")
            lines.append(f"**Impact** — {top.impact}")

        if top.recommendations:
            lines.append("")
            lines.append("**Recommended actions**")
            for item in top.recommendations:
                lines.append(f"- {item}")

        others = [f for f in findings[1:] if f.kind != "healthy"]
        if others:
            lines.append("")
            lines.append("**Also detected**")
            for finding in others[:3]:
                lines.append(f"- [{finding.severity}] {finding.title}")

        measured = [r for r in records if r.ok and r.summary]
        if measured:
            lines.append("")
            lines.append("**Measurements this answer is based on**")
            for record in measured:
                lines.append(f"- `{record.tool}` — {record.summary}")

        lines.append("")
        lines.append(
            f"_Confidence {top.confidence:.0%}. Produced by the deterministic "
            "diagnostics engine from stored telemetry; no language model was used._"
        )
        return "\n".join(lines)


_copilot: PerformanceCopilot | None = None


def get_copilot() -> PerformanceCopilot:
    global _copilot
    if _copilot is None:
        _copilot = PerformanceCopilot()
    return _copilot


def reset_copilot() -> None:
    global _copilot
    _copilot = None
