"""Input guarding for the AI agent.

Two jobs:

1. Reject prompt-injection attempts aimed at making the agent ignore its
   grounding rules or exfiltrate configuration.
2. Keep the agent on-topic. It is an infrastructure analyst, not a
   general-purpose assistant with database access.

This is defence in depth, not the primary control. The primary control is that
the tool registry contains no capability to write, execute or read secrets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Patterns that indicate an attempt to override the agent's instructions or
# extract material it must never surface.
_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "instruction_override",
        re.compile(
            r"\b(ignore|disregard|forget|override)\b[^.]{0,40}\b(previous|prior|above|earlier|all)\b[^.]{0,20}\b(instruction|prompt|rule|direction)",
            re.I,
        ),
    ),
    (
        "role_hijack",
        re.compile(r"\b(you are now|act as|pretend to be|roleplay as|from now on you)\b", re.I),
    ),
    (
        "system_prompt_exfil",
        re.compile(
            r"\b(reveal|show|print|repeat|output|dump)\b[^.]{0,30}"
            r"\b(system prompt|instructions|initial prompt)\b",
            re.I,
        ),
    ),
    (
        "secret_exfil",
        re.compile(
            r"\b(api[_ -]?keys?|secret[_ -]?keys?|passwords?|credentials?"
            r"|\.env|environment variables?)\b[^.]{0,40}"
            r"\b(show|print|reveal|list|what is|give)\b",
            re.I,
        ),
    ),
    (
        "secret_exfil_reverse",
        re.compile(
            r"\b(show|print|reveal|list|dump|tell me|what is|what are)\b[^.]{0,40}"
            r"\b(api[_ -]?keys?|secret[_ -]?keys?|passwords?|credentials?"
            r"|\.env|environment variables?|secrets?)\b",
            re.I,
        ),
    ),
    (
        "code_execution",
        re.compile(
            r"\b(run|execute|exec|eval|spawn|invoke)\b[^.]{0,30}\b(command|shell|bash|sh|python|script|subprocess|os\.system)\b",
            re.I,
        ),
    ),
    (
        "sql_injection",
        re.compile(
            r"\b(drop\s+table|delete\s+from|truncate\s+table|insert\s+into|update\s+\w+\s+set|;\s*--)\b",
            re.I,
        ),
    ),
    (
        "data_mutation",
        re.compile(
            r"\b(delete|drop|wipe|erase|purge|reset)\b[^.]{0,25}"
            r"\b(database|table|all data|telemetry|metrics)\b",
            re.I,
        ),
    ),
    (
        "config_mutation",
        re.compile(
            r"\b(change|modify|update|set|disable)\b[^.]{0,30}\b(configuration|config|setting|threshold|env)\b[^.]{0,20}\b(production|live|prod)\b",
            re.I,
        ),
    ),
]

# The agent answers questions about this platform's telemetry. A question with
# no relationship to that is politely redirected.
# Stems are matched with a trailing \w* so "optimiz" also matches "optimize",
# "optimizing" and "optimization". A bare \b after a stem would never match.
_ON_TOPIC = re.compile(
    r"\b(gpu\w*|vram|memor\w*|cuda|nvidia|inferenc\w*|latenc\w*|throughput|token\w*|"
    r"batch\w*|queue\w*|model\w*|deploy\w*|cost\w*|spend\w*|pric\w*|alert\w*|"
    r"anomal\w*|error\w*|utilis\w*|utiliz\w*|temperatur\w*|thermal|power|clock\w*|"
    r"throttl\w*|perform\w*|bottleneck\w*|optimi\w*|slow\w*|fast\w*|cheap\w*|"
    r"expensiv\w*|regress\w*|degrad\w*|p50|p90|p95|p99|percentile\w*|telemetr\w*|"
    r"metric\w*|monitor\w*|diagnos\w*|health\w*|capacit\w*|scal\w*|cpu|ram|disk\w*|"
    r"network\w*|workload\w*|node\w*|host\w*|cluster\w*|serv\w*|request\w*|"
    r"compute[- ]?bound|memory[- ]?bound|tune|tuning)\b",
    re.I,
)

MAX_MESSAGE_LENGTH = 4000


@dataclass(frozen=True)
class GuardVerdict:
    allowed: bool
    reason: str | None = None
    category: str | None = None
    message: str | None = None


def inspect(message: str) -> GuardVerdict:
    """Screen a user message before it reaches the model or the tools."""
    text = (message or "").strip()

    if not text:
        return GuardVerdict(
            False,
            "empty",
            "invalid",
            "Please ask a question about GPU, inference, cost or alert telemetry.",
        )
    if len(text) > MAX_MESSAGE_LENGTH:
        return GuardVerdict(
            False,
            "too_long",
            "invalid",
            f"That message is too long. Please keep questions under "
            f"{MAX_MESSAGE_LENGTH} characters.",
        )

    for category, pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return GuardVerdict(
                False,
                category,
                "blocked",
                (
                    "I can only answer questions about the telemetry this platform has "
                    "collected. I cannot change my instructions, run commands, modify "
                    "configuration, or disclose credentials."
                ),
            )

    if not _ON_TOPIC.search(text):
        return GuardVerdict(
            False,
            "off_topic",
            "off_topic",
            (
                "I am the NVIDIA Performance Copilot and I answer questions about this "
                "platform's GPU, inference, batching, cost and alert telemetry. "
                "Try asking why GPU utilisation is low, which model is fastest, or "
                "what is driving latency."
            ),
        )

    return GuardVerdict(True)


def sanitize_tool_output(value: str, limit: int = 4000) -> str:
    """Bound tool output before it enters the model context."""
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n[truncated: {len(value) - limit} more characters]"
