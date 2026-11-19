from enum import StrEnum


class ProviderKind(StrEnum):
    DEMO = "demo"
    OPENAI_COMPATIBLE = "openai_compatible"
    VLLM = "vllm"
    HUGGINGFACE = "huggingface"


class ModelStatus(StrEnum):
    """Result of the most recent connection check. UNKNOWN means never checked."""

    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class RequestStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class RequestSource(StrEnum):
    PLAYGROUND = "playground"
    API = "api"
    DEMO_SEED = "demo_seed"


class TokenCountSource(StrEnum):
    """EXACT only when the provider reported every count; anything estimated is ESTIMATED."""

    EXACT = "exact"
    ESTIMATED = "estimated"


def sql_in_list(enum_cls: type[StrEnum]) -> str:
    """Render enum values for a CHECK constraint, e.g. "'a', 'b'"."""
    return ", ".join(f"'{member.value}'" for member in enum_cls)
