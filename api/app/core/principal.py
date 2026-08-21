"""The authenticated caller ('principal') attached to each request."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.core.rbac import has_scope

PrincipalType = Literal["user", "api_key", "anonymous"]


@dataclass(frozen=True)
class Principal:
    """Uniform identity for both JWT users and API-key machine callers."""

    type: PrincipalType
    id: str | None
    label: str | None
    role: str
    scopes: set[str] = field(default_factory=set)

    @property
    def is_authenticated(self) -> bool:
        return self.type != "anonymous"

    def can(self, scope: str) -> bool:
        return has_scope(self.scopes, scope)

    @classmethod
    def anonymous(cls) -> Principal:
        return cls(type="anonymous", id=None, label=None, role="viewer", scopes=set())
