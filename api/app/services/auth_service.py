"""User, session and API-key business logic."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.errors import AuthenticationError, ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.rbac import scopes_for_role, validate_scopes
from app.core.security import (
    create_token,
    generate_api_key,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models.auth import ApiKey, RefreshToken, User
from app.models.enums import UserRole
from app.schemas.auth import ApiKeyCreate, TokenPair, UserCreate

logger = get_logger(__name__)

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


async def create_user(session: AsyncSession, payload: UserCreate) -> User:
    email = payload.email.strip().lower()
    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError("An account with that email already exists.")
    try:
        hashed = hash_password(payload.password)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    user = User(
        email=email,
        full_name=payload.full_name,
        hashed_password=hashed,
        role=payload.role,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    await record_audit(
        action="user.create", resource_type="user", resource_id=user.id, actor_label=email
    )
    return user


async def authenticate(
    session: AsyncSession, email: str, password: str, *, user_agent: str | None = None
) -> tuple[User, TokenPair]:
    """Verify credentials and issue a token pair.

    Failure messages are deliberately identical for unknown accounts and bad
    passwords so the endpoint cannot be used to enumerate users.
    """
    normalized = email.strip().lower()
    result = await session.execute(select(User).where(User.email == normalized))
    user = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    generic = "Invalid email or password."

    if user is None:
        # Spend comparable time so timing does not reveal account existence.
        verify_password(
            password,
            "$argon2id$v=19$m=65536,t=2,p=2$c29tZXNhbHRzYWx0$0000000000000000000000000000000000000000000",
        )
        await record_audit(
            action="auth.login",
            outcome="failure",
            actor_label=normalized,
            detail={"reason": "unknown_account"},
        )
        raise AuthenticationError(generic)

    if user.locked_until and user.locked_until > now:
        raise AuthenticationError(
            "Account is temporarily locked after repeated failed sign-in attempts."
        )

    if not user.is_active:
        await record_audit(
            action="auth.login",
            outcome="failure",
            actor_id=user.id,
            actor_label=normalized,
            detail={"reason": "inactive"},
        )
        raise AuthenticationError(generic)

    if not verify_password(password, user.hashed_password):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
            logger.warning("account_locked", user_id=user.id)
        await session.commit()
        await record_audit(
            action="auth.login",
            outcome="failure",
            actor_id=user.id,
            actor_label=normalized,
            detail={"reason": "bad_password"},
        )
        raise AuthenticationError(generic)

    if password_needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    await session.commit()

    tokens = await issue_tokens(session, user, user_agent=user_agent)
    await record_audit(
        action="auth.login",
        outcome="success",
        actor_type="user",
        actor_id=user.id,
        actor_label=user.email,
    )
    return user, tokens


async def issue_tokens(
    session: AsyncSession, user: User, *, user_agent: str | None = None
) -> TokenPair:
    access, _ = create_token(
        user.id, "access", role=user.role, scopes=sorted(scopes_for_role(user.role))
    )
    refresh, refresh_expires = create_token(user.id, "refresh", role=user.role)
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_refresh_token(refresh),
            expires_at=refresh_expires,
            user_agent=(user_agent or "")[:300] or None,
        )
    )
    await session.commit()
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


async def refresh_tokens(session: AsyncSession, refresh_token: str) -> TokenPair:
    """Rotate a refresh token, revoking the presented one."""
    from app.core.security import decode_token

    payload = decode_token(refresh_token, expected_type="refresh")
    token_hash = hash_refresh_token(refresh_token)

    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored is None:
        raise AuthenticationError("Refresh token is not recognised.")
    if stored.revoked_at is not None:
        # Reuse of a revoked token implies theft: revoke the whole family.
        await revoke_all_for_user(session, stored.user_id)
        logger.warning("refresh_token_reuse_detected", user_id=stored.user_id)
        raise AuthenticationError("Refresh token has been revoked.")
    if stored.expires_at < datetime.now(timezone.utc):
        raise AuthenticationError("Refresh token has expired.")

    user = (
        await session.execute(select(User).where(User.id == payload["sub"]))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthenticationError("Account is inactive or no longer exists.")

    stored.revoked_at = datetime.now(timezone.utc)
    await session.commit()
    return await issue_tokens(session, user)


async def revoke_refresh_token(session: AsyncSession, refresh_token: str) -> None:
    token_hash = hash_refresh_token(refresh_token)
    result = await session.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()
    if stored and stored.revoked_at is None:
        stored.revoked_at = datetime.now(timezone.utc)
        await session.commit()


async def revoke_all_for_user(session: AsyncSession, user_id: str) -> None:
    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
    )
    now = datetime.now(timezone.utc)
    for token in result.scalars().all():
        token.revoked_at = now
    await session.commit()


# --------------------------------------------------------------- API keys ---
async def create_api_key(
    session: AsyncSession, payload: ApiKeyCreate, owner_id: str | None
) -> tuple[ApiKey, str]:
    try:
        scopes = validate_scopes(payload.scopes)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    plaintext, prefix, key_hash = generate_api_key()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=payload.expires_in_days)
        if payload.expires_in_days
        else None
    )
    api_key = ApiKey(
        name=payload.name,
        prefix=prefix,
        key_hash=key_hash,
        scopes=",".join(scopes),
        owner_id=owner_id,
        expires_at=expires_at,
        rate_limit_per_minute=payload.rate_limit_per_minute,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    await record_audit(
        action="api_key.create",
        resource_type="api_key",
        resource_id=api_key.id,
        detail={"name": payload.name, "scopes": scopes},
    )
    return api_key, plaintext


async def revoke_api_key(session: AsyncSession, key_id: str) -> ApiKey:
    result = await session.execute(select(ApiKey).where(ApiKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise NotFoundError("API key not found.")
    api_key.is_active = False
    await session.commit()
    await session.refresh(api_key)
    await record_audit(action="api_key.revoke", resource_type="api_key", resource_id=key_id)
    return api_key


async def ensure_bootstrap_admin(session: AsyncSession) -> None:
    """Create the initial admin account when the users table is empty.

    A password must be supplied via BOOTSTRAP_ADMIN_PASSWORD; the platform
    never ships with a default credential.
    """
    count = await session.scalar(select(func.count()).select_from(User))
    if count:
        return
    if not settings.BOOTSTRAP_ADMIN_PASSWORD:
        logger.warning(
            "bootstrap_admin_skipped",
            reason="BOOTSTRAP_ADMIN_PASSWORD is not set",
            hint="Set it to create the first admin account, or use scripts/create_admin.py",
        )
        return
    try:
        user = User(
            email=settings.BOOTSTRAP_ADMIN_EMAIL.strip().lower(),
            full_name="Bootstrap Administrator",
            hashed_password=hash_password(settings.BOOTSTRAP_ADMIN_PASSWORD),
            role=UserRole.ADMIN.value,
        )
    except ValueError as exc:
        logger.error("bootstrap_admin_failed", error=str(exc))
        return
    session.add(user)
    await session.commit()
    logger.info("bootstrap_admin_created", email=user.email)
