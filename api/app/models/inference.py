"""Model registry, deployments, and inference/batch telemetry."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin
from app.models.enums import DataSource, DeploymentStatus, ModelFramework, Quantization


class MLModel(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A registered inference model profile."""

    __tablename__ = "ml_models"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(60), nullable=False, default="1.0.0")
    display_name: Mapped[str | None] = mapped_column(String(200))
    framework: Mapped[str] = mapped_column(
        String(30), nullable=False, default=ModelFramework.VLLM.value
    )
    parameter_count_b: Mapped[float | None] = mapped_column(Float)
    quantization: Mapped[str] = mapped_column(
        String(20), nullable=False, default=Quantization.FP16.value
    )
    context_length: Mapped[int | None] = mapped_column(Integer)
    max_batch_size: Mapped[int | None] = mapped_column(Integer)
    preferred_batch_sizes: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    deployments: Mapped[list[Deployment]] = relationship(
        back_populates="model", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("name", "version", "data_source", name="uq_ml_models_name_version"),
    )


class Deployment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A model deployed onto specific hardware in a specific environment."""

    __tablename__ = "deployments"

    model_id: Mapped[str] = mapped_column(
        ForeignKey("ml_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    environment: Mapped[str] = mapped_column(String(40), nullable=False, default="production")
    gpu_id: Mapped[str | None] = mapped_column(ForeignKey("gpus.id", ondelete="SET NULL"))
    gpu_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    endpoint_url: Mapped[str | None] = mapped_column(String(400))
    backend: Mapped[str] = mapped_column(String(30), default="local", nullable=False)
    replicas: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_batch_size: Mapped[int | None] = mapped_column(Integer)
    batch_window_ms: Mapped[float | None] = mapped_column(Float)
    tensor_parallel_size: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DeploymentStatus.ACTIVE.value, index=True
    )
    model_load_time_ms: Mapped[float | None] = mapped_column(Float)
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    model: Mapped[MLModel] = relationship(back_populates="deployments")

    __table_args__ = (
        UniqueConstraint("name", "environment", "data_source", name="uq_deployments_name_env"),
        Index("ix_deployments_model_status", "model_id", "status"),
    )


class InferenceRequest(UUIDPrimaryKeyMixin, Base):
    """One observed inference request, recorded by the inference gateway."""

    __tablename__ = "inference_requests"

    deployment_id: Mapped[str | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[str | None] = mapped_column(
        ForeignKey("ml_models.id", ondelete="CASCADE"), index=True
    )
    gpu_id: Mapped[str | None] = mapped_column(ForeignKey("gpus.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    total_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    queue_latency_ms: Mapped[float | None] = mapped_column(Float)
    preprocess_latency_ms: Mapped[float | None] = mapped_column(Float)
    execution_latency_ms: Mapped[float | None] = mapped_column(Float)
    postprocess_latency_ms: Mapped[float | None] = mapped_column(Float)
    time_to_first_token_ms: Mapped[float | None] = mapped_column(Float)

    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    batch_size: Mapped[int | None] = mapped_column(Integer)
    concurrency: Mapped[int | None] = mapped_column(Integer)

    status_code: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    is_error: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    error_type: Mapped[str | None] = mapped_column(String(120))
    client_id: Mapped[str | None] = mapped_column(String(120))
    trace_id: Mapped[str | None] = mapped_column(String(64), index=True)

    __table_args__ = (
        Index("ix_inference_requests_dep_time", "deployment_id", "started_at"),
        Index("ix_inference_requests_model_time", "model_id", "started_at"),
        Index("ix_inference_requests_source_time", "data_source", "started_at"),
    )


class InferenceMetric(UUIDPrimaryKeyMixin, Base):
    """Pre-aggregated inference statistics for a fixed time bucket.

    Dashboards read this table rather than scanning raw requests.
    """

    __tablename__ = "inference_metrics"

    deployment_id: Mapped[str | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    model_id: Mapped[str | None] = mapped_column(
        ForeignKey("ml_models.id", ondelete="CASCADE"), index=True
    )
    bucket_start: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    bucket_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    request_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requests_per_second: Mapped[float | None] = mapped_column(Float)
    avg_latency_ms: Mapped[float | None] = mapped_column(Float)
    min_latency_ms: Mapped[float | None] = mapped_column(Float)
    max_latency_ms: Mapped[float | None] = mapped_column(Float)
    p50_latency_ms: Mapped[float | None] = mapped_column(Float)
    p90_latency_ms: Mapped[float | None] = mapped_column(Float)
    p95_latency_ms: Mapped[float | None] = mapped_column(Float)
    p99_latency_ms: Mapped[float | None] = mapped_column(Float)
    avg_queue_latency_ms: Mapped[float | None] = mapped_column(Float)
    avg_preprocess_latency_ms: Mapped[float | None] = mapped_column(Float)
    avg_execution_latency_ms: Mapped[float | None] = mapped_column(Float)
    avg_postprocess_latency_ms: Mapped[float | None] = mapped_column(Float)
    tokens_per_second: Mapped[float | None] = mapped_column(Float)
    input_tokens_per_second: Mapped[float | None] = mapped_column(Float)
    output_tokens_per_second: Mapped[float | None] = mapped_column(Float)
    total_input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_batch_size: Mapped[float | None] = mapped_column(Float)
    max_batch_size: Mapped[int | None] = mapped_column(Integer)
    avg_concurrency: Mapped[float | None] = mapped_column(Float)
    error_rate: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "bucket_start",
            "bucket_seconds",
            "data_source",
            name="uq_inference_metrics_bucket",
        ),
        Index("ix_inference_metrics_source_bucket", "data_source", "bucket_start"),
    )


class BatchMetric(UUIDPrimaryKeyMixin, Base):
    """Batching behaviour for a time bucket -- the core under-batching signal."""

    __tablename__ = "batch_metrics"

    deployment_id: Mapped[str | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    bucket_start: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    bucket_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    requested_batch_size: Mapped[float | None] = mapped_column(Float)
    effective_batch_size: Mapped[float | None] = mapped_column(Float)
    avg_batch_size: Mapped[float | None] = mapped_column(Float)
    max_batch_size: Mapped[int | None] = mapped_column(Integer)
    configured_max_batch_size: Mapped[int | None] = mapped_column(Integer)
    queue_depth: Mapped[float | None] = mapped_column(Float)
    batch_formation_ms: Mapped[float | None] = mapped_column(Float)
    batch_efficiency: Mapped[float | None] = mapped_column(Float)
    gpu_utilization_pct: Mapped[float | None] = mapped_column(Float)
    throughput_rps: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (
        UniqueConstraint(
            "deployment_id",
            "bucket_start",
            "bucket_seconds",
            "data_source",
            name="uq_batch_metrics_bucket",
        ),
    )
