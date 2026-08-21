"""Password hashing, JWT issuance/verification, and API-key handling."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings
from app.core.errors import AuthenticationError

_hasher = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)

TokenType = Literal["access", "refresh"]


# --------------------------------------------------------------- passwords ---
def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters.")
    if len(password) > 1024:
        raise ValueError("Password exceeds maximum length.")
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def password_needs_rehash(hashed: str) -> bool:
    try:
        return _hasher.check_needs_rehash(hashed)
    except (InvalidHashError, ValueError):
        return True


# -------------------------------------------------------------------- JWT ---
def create_token(
    subject: str,
    token_type: TokenType,
    *,
    role: str | None = None,
    scopes: list[str] | None = None,
    expires_delta: timedelta | None = None,
    jti: str | None = None,
) -> tuple[str, datetime]:
    """Return (encoded_jwt, expires_at)."""
    now = datetime.now(timezone.utc)
    if expires_delta is None:
        expires_delta = (
            timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
            if token_type == "access"
            else timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        )
    expires_at = now + expires_delta
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": jti or secrets.token_urlsafe(16),
        "iss": "nvidia-ai-performance-observatory",
    }
    if role:
        payload["role"] = role
    if scopes:
        payload["scopes"] = scopes
    encoded = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded, expires_at


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer="nvidia-ai-performance-observatory",
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Token is invalid.") from exc
    if expected_type and payload.get("type") != expected_type:
        raise AuthenticationError(f"Expected a {expected_type} token.")
    return payload


# --------------------------------------------------------------- API keys ---
def generate_api_key() -> tuple[str, str, str]:
    """Create a new API key.

    Returns ``(plaintext, prefix, key_hash)``. Only the prefix and hash are
    persisted; the plaintext is shown to the caller exactly once.
    """
    env_tag = "live" if settings.ENVIRONMENT == "production" else "test"
    body = secrets.token_urlsafe(32)
    prefix = f"{settings.API_KEY_PREFIX}_{env_tag}"
    plaintext = f"{prefix}_{body}"
    return plaintext, prefix, hash_api_key(plaintext)


def hash_api_key(plaintext: str) -> str:
    """Deterministic keyed hash so lookups are a single indexed query.

    A keyed HMAC (rather than a bare digest) means a leaked database alone is
    not sufficient to verify guesses offline without also leaking SECRET_KEY.
    """
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        plaintext.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
