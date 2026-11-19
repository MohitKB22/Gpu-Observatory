import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import HealthStatus, sql_in_list


class HealthCheck(Base):
    __tablename__ = "health_checks"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in_list(HealthStatus)})", name="status_valid"),
        Index("ix_health_checks_model_id_checked_at", "model_id", "checked_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("registered_models.id", ondelete="CASCADE"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    status: Mapped[str] = mapped_column(String(16))
    latency_ms: Mapped[float | None] = mapped_column(Float)
    error_kind: Mapped[str | None] = mapped_column(String(32))
    error_message: Mapped[str | None] = mapped_column(Text)
