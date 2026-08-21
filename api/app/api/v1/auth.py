"""Authentication, user administration and API-key endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select

from app.core.audit import record_audit
from app.core.config import settings
from app.core.deps import CurrentPrincipal, DbSession, PaginationParam, require_role
from app.core.errors import AuthorizationError, NotFoundError
from app.core.principal import Principal
from app.models.auth import ApiKey, AuditLog, User
from app.models.enums import UserRole
from app.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    AuditLogOut,
    LoginRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.schemas.common import MessageResponse, Page, PageMeta
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

AdminOnly = Annotated[Principal, Depends(require_role(UserRole.ADMIN))]


@router.post("/login", response_model=TokenPair, summary="Sign in and receive tokens")
async def login(payload: LoginRequest, request: Request, session: DbSession) -> TokenPair:
    _user, tokens = await auth_service.authenticate(
        session,
        payload.email,
        payload.password,
        user_agent=request.headers.get("user-agent"),
    )
    return tokens


@router.post("/refresh", response_model=TokenPair, summary="Rotate a refresh token")
async def refresh(payload: RefreshRequest, session: DbSession) -> TokenPair:
    return await auth_service.refresh_tokens(session, payload.refresh_token)


@router.post("/logout", response_model=MessageResponse, summary="Revoke a refresh token")
async def logout(payload: RefreshRequest, session: DbSession) -> MessageResponse:
    await auth_service.revoke_refresh_token(session, payload.refresh_token)
    return MessageResponse(message="Signed out.")


@router.get("/me", response_model=UserOut, summary="Current user")
async def me(principal: CurrentPrincipal, session: DbSession) -> UserOut:
    if principal.type != "user" or not principal.id:
        raise AuthorizationError("This endpoint is only available to user sessions.")
    user = (await session.execute(select(User).where(User.id == principal.id))).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found.")
    return UserOut.model_validate(user)


@router.post(
    "/users",
    response_model=UserOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user (admin)",
)
async def create_user(payload: UserCreate, session: DbSession, _admin: AdminOnly) -> UserOut:
    user = await auth_service.create_user(session, payload)
    return UserOut.model_validate(user)


@router.get("/users", response_model=Page[UserOut], summary="List users (admin)")
async def list_users(
    session: DbSession, pagination: PaginationParam, _admin: AdminOnly
) -> Page[UserOut]:
    total = int(await session.scalar(select(func.count()).select_from(User)) or 0)
    rows = list(
        (
            await session.execute(
                select(User)
                .order_by(User.created_at.desc())
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page[UserOut](
        items=[UserOut.model_validate(r) for r in rows],
        meta=PageMeta(
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(rows) < total,
        ),
    )


@router.patch("/users/{user_id}", response_model=UserOut, summary="Update a user (admin)")
async def update_user(
    user_id: str, payload: UserUpdate, session: DbSession, admin: AdminOnly
) -> UserOut:
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found.")
    if user.id == admin.id and payload.is_active is False:
        raise AuthorizationError("You cannot deactivate your own account.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await session.commit()
    await session.refresh(user)
    await record_audit(
        action="user.update",
        resource_type="user",
        resource_id=user_id,
        actor_id=admin.id,
        actor_label=admin.label,
    )
    return UserOut.model_validate(user)


@router.post(
    "/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create an API key (admin)",
)
async def create_api_key(
    payload: ApiKeyCreate, session: DbSession, admin: AdminOnly
) -> ApiKeyCreated:
    api_key, plaintext = await auth_service.create_api_key(session, payload, admin.id)
    return ApiKeyCreated(api_key=ApiKeyOut.model_validate(api_key), plaintext_key=plaintext)


@router.get("/api-keys", response_model=Page[ApiKeyOut], summary="List API keys (admin)")
async def list_api_keys(
    session: DbSession, pagination: PaginationParam, _admin: AdminOnly
) -> Page[ApiKeyOut]:
    total = int(await session.scalar(select(func.count()).select_from(ApiKey)) or 0)
    rows = list(
        (
            await session.execute(
                select(ApiKey)
                .order_by(ApiKey.created_at.desc())
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page[ApiKeyOut](
        items=[ApiKeyOut.model_validate(r) for r in rows],
        meta=PageMeta(
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(rows) < total,
        ),
    )


@router.delete("/api-keys/{key_id}", response_model=ApiKeyOut, summary="Revoke an API key (admin)")
async def revoke_api_key(key_id: str, session: DbSession, _admin: AdminOnly) -> ApiKeyOut:
    api_key = await auth_service.revoke_api_key(session, key_id)
    return ApiKeyOut.model_validate(api_key)


@router.get("/audit", response_model=Page[AuditLogOut], summary="Audit log (admin)")
async def audit_log(
    session: DbSession, pagination: PaginationParam, _admin: AdminOnly
) -> Page[AuditLogOut]:
    total = int(await session.scalar(select(func.count()).select_from(AuditLog)) or 0)
    rows = list(
        (
            await session.execute(
                select(AuditLog)
                .order_by(AuditLog.occurred_at.desc())
                .limit(pagination.limit)
                .offset(pagination.offset)
            )
        )
        .scalars()
        .all()
    )
    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(r) for r in rows],
        meta=PageMeta(
            total=total,
            limit=pagination.limit,
            offset=pagination.offset,
            has_more=pagination.offset + len(rows) < total,
        ),
    )


@router.get("/config", summary="Public auth configuration")
async def auth_config() -> dict:
    """Lets the frontend know whether to render a login screen."""
    return {
        "auth_enabled": settings.AUTH_ENABLED,
        "access_token_lifetime_seconds": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "api_key_prefix": settings.API_KEY_PREFIX,
    }
