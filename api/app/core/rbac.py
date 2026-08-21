"""Role-based access control and scope resolution."""

from __future__ import annotations

from app.models.enums import Scope, UserRole

# A role expands to a fixed set of scopes. API keys may hold a narrower set.
ROLE_SCOPES: dict[str, set[str]] = {
    UserRole.VIEWER.value: {
        Scope.TELEMETRY_READ.value,
        Scope.MODELS_READ.value,
        Scope.ALERTS_READ.value,
        Scope.DIAGNOSTICS_READ.value,
        Scope.COST_READ.value,
    },
    UserRole.OPERATOR.value: {
        Scope.TELEMETRY_READ.value,
        Scope.TELEMETRY_WRITE.value,
        Scope.MODELS_READ.value,
        Scope.MODELS_WRITE.value,
        Scope.ALERTS_READ.value,
        Scope.ALERTS_WRITE.value,
        Scope.DIAGNOSTICS_READ.value,
        Scope.DIAGNOSTICS_RUN.value,
        Scope.AGENT_CHAT.value,
        Scope.COST_READ.value,
    },
    UserRole.ADMIN.value: {s.value for s in Scope},
}

ROLE_ORDER = [UserRole.VIEWER.value, UserRole.OPERATOR.value, UserRole.ADMIN.value]


def scopes_for_role(role: str) -> set[str]:
    return set(ROLE_SCOPES.get(role, ROLE_SCOPES[UserRole.VIEWER.value]))


def role_at_least(role: str, minimum: str) -> bool:
    try:
        return ROLE_ORDER.index(role) >= ROLE_ORDER.index(minimum)
    except ValueError:
        return False


def has_scope(granted: set[str], required: str) -> bool:
    return Scope.ADMIN.value in granted or required in granted


def validate_scopes(requested: list[str]) -> list[str]:
    """Reject unknown scopes rather than silently dropping them."""
    valid = {s.value for s in Scope}
    unknown = [s for s in requested if s not in valid]
    if unknown:
        raise ValueError(f"Unknown scopes: {', '.join(sorted(unknown))}")
    return sorted(set(requested))
