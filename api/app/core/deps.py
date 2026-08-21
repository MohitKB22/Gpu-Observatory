"""FastAPI dependencies: authentication, authorisation and common query params."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthenticationError, AuthorizationError
from app.core.principal import Principal
from app.core.rbac import scopes_for_role
from app.core.security import decode_token, hash_api_key
from app.db.session import get_session
from app.models.auth import ApiKey, User
from app.models.enums import DataSource, Scope, UserRole

# auto_error=False so unauthenticated requests produce our error envelope.
_bearer = HTTPBearer(auto_error=False, description="JWT access token or API key")

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def _principal_from_api_key(token: str, session: AsyncSession) -> Principal | None:
    if not token.startswith(f"{settings.API_KEY_PREFIX}_"):
        return None
    key_hash = hash_api_key(token)
    result = await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise AuthenticationError("API key is not recognised.")
    if not api_key.is_active:
        raise AuthenticationError("API key has been revoked.")
    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        raise AuthenticationError("API key has expired.")

    api_key.last_used_at = datetime.now(timezone.utc)
    await session.commit()

    return Principal(
        type="api_key",
        id=api_key.id,
        label=api_key.name,
        role=UserRole.OPERATOR.value,
        scopes=set(api_key.scope_list),
    )


async def _principal_from_jwt(token: str, session: AsyncSession) -> Principal:
    payload = decode_token(token, expected_type="access")
    user_id = payload.get("sub")
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationError("Account is inactive or no longer exists.")
    return Principal(
        type="user",
        id=user.id,
        label=user.email,
        role=user.role,
        scopes=scopes_for_role(user.role),
    )


async def get_principal(
    request: Request,
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> Principal:
    """Resolve the caller from either an API key or a JWT access token.

    When ``AUTH_ENABLED`` is false (local development only) every caller is
    treated as an admin; this is logged loudly at startup.
    """
    if not settings.AUTH_ENABLED:
        return Principal(
            type="user",
            id="auth-disabled",
            label="auth-disabled",
            role=UserRole.ADMIN.value,
            scopes=scopes_for_role(UserRole.ADMIN.value),
        )

    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Authentication credentials were not provided.")

    token = credentials.credentials
    principal = await _principal_from_api_key(token, session)
    if principal is None:
        principal = await _principal_from_jwt(token, session)
    request.state.principal = principal
    return principal


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def require_scope(scope: Scope | str):
    """Dependency factory enforcing a single scope."""
    required = scope.value if isinstance(scope, Scope) else scope

    async def _dependency(principal: CurrentPrincipal) -> Principal:
        if not principal.can(required):
            raise AuthorizationError(
                f"This action requires the '{required}' scope.",
                details={"required_scope": required, "role": principal.role},
            )
        return principal

    return _dependency


def require_role(minimum: UserRole | str):
    """Dependency factory enforcing a minimum role."""
    from app.core.rbac import role_at_least

    needed = minimum.value if isinstance(minimum, UserRole) else minimum

    async def _dependency(principal: CurrentPrincipal) -> Principal:
        if not role_at_least(principal.role, needed):
            raise AuthorizationError(
                f"This action requires the '{needed}' role or higher.",
                details={"required_role": needed, "role": principal.role},
            )
        return principal

    return _dependency


async def get_data_source(
    source: Annotated[
        str | None,
        Query(
            description=(
                "Telemetry namespace to read. Demo data is never mixed with "
                "production data. Defaults to the server's configured mode."
            ),
            pattern="^(production|demo)$",
        ),
    ] = None,
) -> str:
    """Resolve which telemetry namespace a read should target."""
    if source:
        return source
    return DataSource.DEMO.value if settings.DEMO_MODE else DataSource.PRODUCTION.value


DataSourceParam = Annotated[str, Depends(get_data_source)]


@dataclass(frozen=True)
class Pagination:
    """Standard limit/offset pagination with a hard upper bound."""

    limit: int = 100
    offset: int = 0


def pagination_params(
    limit: int = Query(100, ge=1, le=1000, description="Maximum rows to return"),
    offset: int = Query(0, ge=0, description="Rows to skip"),
) -> Pagination:
    """Function dependency rather than a class, so the postponed annotations
    enabled in this module cannot leave unresolved forward references in the
    generated OpenAPI schema."""
    return Pagination(limit=limit, offset=offset)


PaginationParam = Annotated[Pagination, Depends(pagination_params)]


async def db_session_dep() -> AsyncGenerator[AsyncSession, None]:  # pragma: no cover
    async for session in get_session():
        yield session
