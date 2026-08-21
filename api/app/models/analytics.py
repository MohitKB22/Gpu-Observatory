"""Anomalies, alerts, diagnoses, pricing and workload models."""

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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UTCDateTime, UUIDPrimaryKeyMixin
from app.models.enums import (
    AlertState,
    AnomalyMethod,
    DataSource,
    DiagnosisEngine,
    PricingKind,
    Severity,
    WorkloadStatus,
)


class Anomaly(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A statistically detected deviation, retained as an event."""

    __tablename__ = "anomalies"

    detected_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    metric_kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    method: Mapped[str] = mapped_column(
        String(30), nullable=False, default=AnomalyMethod.ZSCORE.value
    )
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default=Severity.LOW.value, index=True
    )
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    entity_type: Mapped[str | None] = mapped_column(String(40))  # gpu|deployment|host
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    entity_label: Mapped[str | None] = mapped_column(String(200))

    observed_value: Mapped[float] = mapped_column(Float, nullable=False)
    expected_value: Mapped[float | None] = mapped_column(Float)
    deviation: Mapped[float | None] = mapped_column(Float)
    score: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    window_seconds: Mapped[int | None] = mapped_column(Integer)
    sample_count: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index("ix_anomalies_source_time", "data_source", "detected_at"),
        Index("ix_anomalies_metric_time", "metric_kind", "detected_at"),
    )


class AlertRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A configurable threshold rule evaluated by the alert engine."""

    __tablename__ = "alert_rules"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    condition: Mapped[str] = mapped_column(String(60), nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default=Severity.MEDIUM.value)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    for_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    cooldown_seconds: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )
    last_fired_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Alert(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A fired alert instance with an active -> acknowledged -> resolved lifecycle."""

    __tablename__ = "alerts"

    rule_id: Mapped[str | None] = mapped_column(
        ForeignKey("alert_rules.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    condition: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default=Severity.MEDIUM.value, index=True
    )
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AlertState.ACTIVE.value, index=True
    )
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    entity_label: Mapped[str | None] = mapped_column(String(200))

    observed_value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    message: Mapped[str | None] = mapped_column(Text)

    triggered_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    acknowledged_by: Mapped[str | None] = mapped_column(String(320))
    acknowledge_note: Mapped[str | None] = mapped_column(Text)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    resolve_reason: Mapped[str | None] = mapped_column(String(300))

    __table_args__ = (
        Index("ix_alerts_state_time", "state", "triggered_at"),
        Index("ix_alerts_source_state", "data_source", "state"),
    )


class Diagnosis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A stored root-cause diagnosis produced by the rules engine and/or agent."""

    __tablename__ = "diagnoses"

    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default=Severity.INFO.value, index=True
    )
    engine: Mapped[str] = mapped_column(
        String(20), nullable=False, default=DiagnosisEngine.RULES.value
    )
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.PRODUCTION.value, index=True
    )

    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    entity_label: Mapped[str | None] = mapped_column(String(200))

    root_cause: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False, default="[]")  # JSON array
    metrics: Mapped[str] = mapped_column(Text, nullable=False, default="{}")  # JSON object
    impact: Mapped[str | None] = mapped_column(Text)
    recommendations: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    window_seconds: Mapped[int | None] = mapped_column(Integer)
    narrative: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_diagnoses_source_time", "data_source", "generated_at"),)


class PricingProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Configurable pricing. Cloud pricing is never hardcoded as universal truth."""

    __tablename__ = "pricing_profiles"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(
        String(30), nullable=False, default=PricingKind.CLOUD_HOURLY.value
    )
    gpu_model: Mapped[str | None] = mapped_column(String(160), index=True)
    provider: Mapped[str | None] = mapped_column(String(120))
    region: Mapped[str | None] = mapped_column(String(80))
    cost_per_gpu_hour: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    energy_cost_per_kwh: Mapped[float | None] = mapped_column(Float)
    amortization_months: Mapped[int | None] = mapped_column(Integer)
    hardware_capex: Mapped[float | None] = mapped_column(Float)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    effective_from: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Workload(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A synthetic load-generation run used to exercise the diagnostics engine."""

    __tablename__ = "workloads"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    profile: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=WorkloadStatus.PENDING.value, index=True
    )
    data_source: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DataSource.DEMO.value, index=True
    )
    deployment_id: Mapped[str | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="SET NULL"), index=True
    )

    target_rps: Mapped[float | None] = mapped_column(Float)
    concurrency: Mapped[int | None] = mapped_column(Integer)
    batch_size: Mapped[int | None] = mapped_column(Integer)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    scenario: Mapped[str | None] = mapped_column(String(40))

    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    requests_generated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors_generated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[str | None] = mapped_column(Text)  # JSON object
