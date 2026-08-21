"""Authentication and API-key schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.common import ORMModel


class LoginRequest(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds.")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10, max_length=4096)


class UserCreate(BaseModel):
    email: str = Field(max_length=320)
    password: str = Field(min_length=12, max_length=1024)
    full_name: str | None = Field(default=None, max_length=200)
    role: str = Field(default="viewer", pattern="^(viewer|operator|admin)$")

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if "@" not in v or v.startswith("@") or v.endswith("@") or " " in v:
            raise ValueError("A valid email address is required.")
        return v.strip().lower()


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str | None = None
    role: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    role: str | None = Field(default=None, pattern="^(viewer|operator|admin)$")
    is_active: bool | None = None


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    scopes: list[str] = Field(default_factory=list, max_length=32)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)
    rate_limit_per_minute: int | None = Field(default=None, ge=1, le=100000)


class ApiKeyOut(ORMModel):
    id: str
    name: str
    prefix: str
    scopes: str
    is_active: bool
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime


class ApiKeyCreated(BaseModel):
    """Returned once, at creation. The plaintext key is never retrievable again."""

    api_key: ApiKeyOut
    plaintext_key: str = Field(description="Store this now -- it cannot be retrieved later.")


class AuditLogOut(ORMModel):
    id: str
    occurred_at: datetime
    actor_type: str
    actor_label: str | None = None
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    outcome: str
    request_id: str | None = None
    source_ip: str | None = None


__all__ = [
    "ApiKeyCreate",
    "ApiKeyCreated",
    "ApiKeyOut",
    "AuditLogOut",
    "EmailStr",
    "LoginRequest",
    "RefreshRequest",
    "TokenPair",
    "UserCreate",
    "UserOut",
    "UserUpdate",
]
