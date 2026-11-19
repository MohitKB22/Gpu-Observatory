import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.enums import RequestSource, RequestStatus, TokenCountSource, sql_in_list


class InferenceRequest(Base):
    """One inference attempt: what was sent, what came back, and how it ended.

    Model name and provider are copied onto the row so history stays readable after a
    model is renamed or deleted.
    """

    __tablename__ = "inference_requests"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in_list(RequestStatus)})", name="status_valid"),
        CheckConstraint(f"source IN ({sql_in_list(RequestSource)})", name="source_valid"),
        Index("ix_inference_requests_model_id_created_at", "model_id", "created_at"),
        Index("ix_inference_requests_is_demo_created_at", "is_demo", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    model_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("registered_models.id", ondelete="SET NULL"))
    model_name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

    status: Mapped[str] = mapped_column(String(16))
    prompt: Mapped[str] = mapped_column(Text)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    temperature: Mapped[float] = mapped_column(Float)
    max_tokens: Mapped[int] = mapped_column(Integer)

    error_kind: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
    upstream_status_code: Mapped[int | None] = mapped_column(Integer)

    metrics: Mapped["RequestMetrics"] = relationship(
        back_populates="request", lazy="joined", uselist=False, cascade="all, delete-orphan"
    )


class RequestMetrics(Base):
    """Numeric measurements for one request.

    Kept in a narrow table, separate from the prompt/response text, so analytics queries
    scan small rows instead of large text columns.
    """

    __tablename__ = "request_metrics"
    __table_args__ = (
        CheckConstraint(
            f"token_count_source IS NULL OR token_count_source IN ({sql_in_list(TokenCountSource)})",
            name="token_count_source_valid",
        ),
    )

    request_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("inference_requests.id", ondelete="CASCADE"), primary_key=True
    )
    latency_ms: Mapped[float] = mapped_column(Float)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    total_tokens: Mapped[int | None] = mapped_column(Integer)
    token_count_source: Mapped[str | None] = mapped_column(String(16))
    tokens_per_second: Mapped[float | None] = mapped_column(Float)

    request: Mapped[InferenceRequest] = relationship(back_populates="metrics")
