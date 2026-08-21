"""Anomaly, alert, diagnosis, cost and workload schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AnomalyOut(ORMModel):
    id: str
    detected_at: datetime
    metric_kind: str
    method: str
    severity: str
    data_source: str
    entity_type: str | None = None
    entity_id: str | None = None
    entity_label: str | None = None
    observed_value: float
    expected_value: float | None = None
    deviation: float | None = None
    score: float | None = None
    threshold: float | None = None
    window_seconds: int | None = None
    sample_count: int | None = None
    description: str | None = None


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    condition: str = Field(
        pattern=(
            "^(gpu_utilization_below|vram_above|temperature_above|p95_latency_above"
            "|throughput_below|error_rate_above|cost_above|power_above)$"
        )
    )
    threshold: float = Field(ge=-1e9, le=1e9)
    severity: str = Field(default="medium", pattern="^(info|low|medium|high|critical)$")
    entity_type: str | None = Field(default=None, max_length=40)
    entity_id: str | None = Field(default=None, max_length=36)
    for_seconds: int = Field(default=60, ge=0, le=86400)
    cooldown_seconds: int = Field(default=300, ge=0, le=86400)
    is_enabled: bool = True
    description: str | None = Field(default=None, max_length=2000)


class AlertRuleOut(ORMModel):
    id: str
    name: str
    condition: str
    threshold: float
    severity: str
    entity_type: str | None = None
    entity_id: str | None = None
    for_seconds: int
    cooldown_seconds: int
    is_enabled: bool
    description: str | None = None
    data_source: str
    last_fired_at: datetime | None = None
    created_at: datetime


class AlertOut(ORMModel):
    id: str
    rule_id: str | None = None
    title: str
    condition: str
    severity: str
    state: str
    data_source: str
    entity_type: str | None = None
    entity_id: str | None = None
    entity_label: str | None = None
    observed_value: float | None = None
    threshold: float | None = None
    message: str | None = None
    triggered_at: datetime
    acknowledged_at: datetime | None = None
    acknowledged_by: str | None = None
    acknowledge_note: str | None = None
    resolved_at: datetime | None = None
    resolve_reason: str | None = None


class AlertAcknowledge(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AlertSummary(BaseModel):
    active: int = 0
    acknowledged: int = 0
    resolved_24h: int = 0
    by_severity: dict[str, int] = Field(default_factory=dict)


class DiagnosisRequest(BaseModel):
    """Ask the diagnostics engine to analyse a window."""

    range: str = Field(default="1h", max_length=16)
    entity_type: str | None = Field(default=None, pattern="^(gpu|deployment|host)$")
    entity_id: str | None = Field(default=None, max_length=36)
    use_llm: bool = Field(
        default=True,
        description=(
            "Enrich the deterministic result with an LLM narrative when a "
            "provider is configured. Rules always run regardless."
        ),
    )
    persist: bool = True


class DiagnosisOut(BaseModel):
    """The structured diagnosis contract from specification section 14."""

    id: str | None = None
    title: str
    severity: str
    kind: str
    root_cause: str
    evidence: list[str] = Field(default_factory=list)
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)
    impact: str | None = None
    recommendations: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    engine: str = "rules"
    entity_type: str | None = None
    entity_id: str | None = None
    entity_label: str | None = None
    narrative: str | None = None
    data_source: str = "production"
    window_seconds: int | None = None
    generated_at: datetime


class DiagnosisReport(BaseModel):
    findings: list[DiagnosisOut]
    analysed_window: str
    data_source: str
    engine: str
    generated_at: datetime


class CostBreakdownItem(BaseModel):
    label: str
    entity_id: str | None = None
    gpu_hours: float | None = None
    cost: float
    share_pct: float | None = None


class CostSummary(BaseModel):
    """All cost figures are estimates derived from configurable pricing."""

    data_source: str
    currency: str
    range_label: str
    start: datetime
    end: datetime
    pricing_profile: str
    cost_per_gpu_hour: float
    is_estimate: bool = True
    gpu_hours: float = 0.0
    total_cost: float = 0.0
    energy_cost: float | None = None
    request_count: int = 0
    total_tokens: int = 0
    cost_per_request: float | None = None
    cost_per_1k_tokens: float | None = None
    cost_per_1m_tokens: float | None = None
    daily_cost: float | None = None
    projected_monthly_cost: float | None = None
    breakdown: list[CostBreakdownItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PricingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(default="cloud_hourly", pattern="^(cloud_hourly|on_prem_amortized|energy)$")
    gpu_model: str | None = Field(default=None, max_length=160)
    provider: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, max_length=80)
    cost_per_gpu_hour: float = Field(ge=0, le=1_000_000)
    currency: str = Field(default="USD", max_length=8)
    energy_cost_per_kwh: float | None = Field(default=None, ge=0, le=100)
    amortization_months: int | None = Field(default=None, ge=1, le=600)
    hardware_capex: float | None = Field(default=None, ge=0)
    is_default: bool = False
    notes: str | None = Field(default=None, max_length=2000)


class PricingOut(ORMModel):
    id: str
    name: str
    kind: str
    gpu_model: str | None = None
    provider: str | None = None
    region: str | None = None
    cost_per_gpu_hour: float
    currency: str
    energy_cost_per_kwh: float | None = None
    amortization_months: int | None = None
    hardware_capex: float | None = None
    is_default: bool
    is_estimate: bool
    notes: str | None = None
    created_at: datetime


class WorkloadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    profile: str = Field(
        pattern=(
            "^(low_concurrency|high_concurrency|small_batch|large_batch"
            "|latency_spike|memory_pressure)$"
        )
    )
    deployment_id: str | None = Field(default=None, max_length=36)
    target_rps: float | None = Field(default=None, gt=0, le=1_000_000)
    concurrency: int | None = Field(default=None, ge=1, le=100000)
    batch_size: int | None = Field(default=None, ge=1, le=8192)
    duration_seconds: int = Field(default=60, ge=1, le=86400)
    scenario: str | None = Field(default=None, max_length=40)


class WorkloadOut(ORMModel):
    id: str
    name: str
    profile: str
    status: str
    data_source: str
    deployment_id: str | None = None
    target_rps: float | None = None
    concurrency: int | None = None
    batch_size: int | None = None
    duration_seconds: int | None = None
    scenario: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    requests_generated: int
    errors_generated: int
    error_message: str | None = None
    created_at: datetime


class DemoStateOut(BaseModel):
    enabled: bool
    scenario: str
    available_scenarios: list[str]
    gpu_count: int
    interval_seconds: float
    running: bool
    samples_generated: int
    started_at: datetime | None = None
    description: str | None = None


class DemoControl(BaseModel):
    scenario: str = Field(
        pattern=(
            "^(healthy|under_batching|vram_pressure|cpu_bottleneck"
            "|latency_spike|throughput_degradation|thermal_throttling)$"
        )
    )
