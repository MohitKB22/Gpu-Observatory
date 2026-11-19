import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ModelStatus, ProviderKind, sql_in_list


class RegisteredModel(Base):
    """A model endpoint registered in the Observatory.

    `is_enabled` only controls whether the Observatory sends traffic to the endpoint.
    It does not deploy or stop anything on the serving infrastructure.
    """

    __tablename__ = "registered_models"
    # Fetch server-generated values (created_at, updated_at) with RETURNING on insert/update.
    # Async sessions cannot lazily reload expired attributes afterwards.
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(f"provider IN ({sql_in_list(ProviderKind)})", name="provider_valid"),
        CheckConstraint(f"status IN ({sql_in_list(ModelStatus)})", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    provider: Mapped[str] = mapped_column(String(32))
    model_identifier: Mapped[str] = mapped_column(String(200))
    endpoint_url: Mapped[str | None] = mapped_column(String(500))
    encrypted_api_key: Mapped[str | None] = mapped_column(Text)
    timeout_seconds: Mapped[float] = mapped_column(Float, default=60.0)
    description: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    status: Mapped[str] = mapped_column(String(16), default=ModelStatus.UNKNOWN)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_check_latency_ms: Mapped[float | None] = mapped_column(Float)
    last_error: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def is_demo(self) -> bool:
        return self.provider == ProviderKind.DEMO

    @property
    def has_api_key(self) -> bool:
        return bool(self.encrypted_api_key)
