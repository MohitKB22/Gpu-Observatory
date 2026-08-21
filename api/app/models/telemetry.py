"""GPU and system telemetry models."""

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
from app.models.enums import DataSource


class Gpu(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A physical (or demo) GPU device discovered by a telemetry agent."""

    __tablename__ = "gpus"

    uuid: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    host: Mapped[str] = mapped_column(String(200), nullable=False, default="localhost", index=True)
    driver_version: Mapped[str | None] = mapped_column(String(60))
    cuda_version: Mapped[str | None] = mapped_column(String(30))
    vbios_version: Mapped[str | None] = mapped_column(String(60))
    serial: Mapped[str | None] = mapped_column(String(60))
    total_memory_mb: Mapped[float | None] = mapped_column(Float)
    power_limit_w: Mapped[float | None] = mapped_column(Float)
    max_clock_mhz: Mapped[int | None] = mapped_column(Integer)
    max_memory_clock_mhz: Mapped[int | None] = mapped_column(Integer)
    compute_capability: Mapped[str | None] = mapped_column(String(16))
    pcie_gen: Mapped[int | None] = mapped_column(Integer)
    pcie_width: Mapped[int | None] = mapped_column(Integer)
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)

    metrics: Mapped[list[GpuMetric]] = relationship(
        back_populates="gpu", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("uuid", "data_source", name="uq_gpus_uuid_source"),
        Index("ix_gpus_source_index", "data_source", "index"),
    )


class GpuMetric(UUIDPrimaryKeyMixin, Base):
    """A single GPU telemetry sample."""

    __tablename__ = "gpu_metrics"

    gpu_id: Mapped[str] = mapped_column(
        ForeignKey("gpus.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    utilization_pct: Mapped[float | None] = mapped_column(Float)
    memory_utilization_pct: Mapped[float | None] = mapped_column(Float)
    memory_used_mb: Mapped[float | None] = mapped_column(Float)
    memory_free_mb: Mapped[float | None] = mapped_column(Float)
    memory_total_mb: Mapped[float | None] = mapped_column(Float)
    temperature_c: Mapped[float | None] = mapped_column(Float)
    power_w: Mapped[float | None] = mapped_column(Float)
    power_limit_w: Mapped[float | None] = mapped_column(Float)
    sm_clock_mhz: Mapped[int | None] = mapped_column(Integer)
    memory_clock_mhz: Mapped[int | None] = mapped_column(Integer)
    fan_speed_pct: Mapped[float | None] = mapped_column(Float)
    pcie_tx_kb_s: Mapped[float | None] = mapped_column(Float)
    pcie_rx_kb_s: Mapped[float | None] = mapped_column(Float)
    throttle_reasons: Mapped[str | None] = mapped_column(Text)
    ecc_errors: Mapped[int | None] = mapped_column(Integer)

    gpu: Mapped[Gpu] = relationship(back_populates="metrics")

    __table_args__ = (
        Index("ix_gpu_metrics_gpu_time", "gpu_id", "recorded_at"),
        Index("ix_gpu_metrics_source_time", "data_source", "recorded_at"),
    )


class GpuProcess(UUIDPrimaryKeyMixin, Base):
    """Process-level GPU occupancy observed at a point in time."""

    __tablename__ = "gpu_processes"

    gpu_id: Mapped[str] = mapped_column(
        ForeignKey("gpus.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    process_name: Mapped[str | None] = mapped_column(String(255))
    used_memory_mb: Mapped[float | None] = mapped_column(Float)
    sm_utilization_pct: Mapped[float | None] = mapped_column(Float)
    workload_label: Mapped[str | None] = mapped_column(String(160))
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    __table_args__ = (Index("ix_gpu_processes_gpu_time", "gpu_id", "recorded_at"),)


class SystemMetric(UUIDPrimaryKeyMixin, Base):
    """Host CPU / memory / disk / network sample."""

    __tablename__ = "system_metrics"

    host: Mapped[str] = mapped_column(String(200), nullable=False, default="localhost", index=True)
    recorded_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    cpu_utilization_pct: Mapped[float | None] = mapped_column(Float)
    per_core_utilization: Mapped[str | None] = mapped_column(Text)  # JSON array
    core_count: Mapped[int | None] = mapped_column(Integer)
    load_avg_1m: Mapped[float | None] = mapped_column(Float)
    load_avg_5m: Mapped[float | None] = mapped_column(Float)
    load_avg_15m: Mapped[float | None] = mapped_column(Float)
    ram_total_mb: Mapped[float | None] = mapped_column(Float)
    ram_used_mb: Mapped[float | None] = mapped_column(Float)
    ram_utilization_pct: Mapped[float | None] = mapped_column(Float)
    swap_total_mb: Mapped[float | None] = mapped_column(Float)
    swap_used_mb: Mapped[float | None] = mapped_column(Float)
    disk_total_gb: Mapped[float | None] = mapped_column(Float)
    disk_used_gb: Mapped[float | None] = mapped_column(Float)
    disk_utilization_pct: Mapped[float | None] = mapped_column(Float)
    net_sent_kb_s: Mapped[float | None] = mapped_column(Float)
    net_recv_kb_s: Mapped[float | None] = mapped_column(Float)
    process_count: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (Index("ix_system_metrics_host_time", "host", "recorded_at"),)
