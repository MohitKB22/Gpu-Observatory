"""Statistical anomaly detection."""

from app.models.enums import DataSource
from app.services.anomaly_service import (
    detect_ewma,
    detect_percentile,
    detect_zscore,
    scan,
)

STABLE = [50.0 + (i % 3) * 0.5 for i in range(40)]


def test_stable_series_produces_no_anomaly():
    assert detect_zscore(STABLE, metric_kind="gpu_utilization") is None


def test_short_series_is_ignored():
    """Below the minimum sample count there is no baseline to compare against."""
    assert detect_zscore([1.0, 2.0, 3.0], metric_kind="gpu_utilization") is None


def test_spike_is_detected_with_evidence():
    found = detect_zscore([*STABLE, 400.0], metric_kind="latency_p95", label="P95 latency")
    assert found is not None
    assert found.severity in {"medium", "high", "critical"}
    assert found.observed_value == 400.0
    assert found.expected_value is not None
    assert "P95 latency" in found.description


def test_direction_filter_ignores_improvements():
    """A drop in latency is good news, not an anomaly."""
    assert detect_zscore([*STABLE, 1.0], metric_kind="latency_p95", higher_is_worse=True) is None
    assert (
        detect_zscore([*STABLE, 1.0], metric_kind="throughput", higher_is_worse=False) is not None
    )


def test_ewma_detects_divergence():
    found = detect_ewma([*STABLE, 250.0], metric_kind="latency_p95")
    assert found is not None
    assert found.method == "ewma"


def test_percentile_detector_flags_ceiling_breach():
    found = detect_percentile([*STABLE, 120.0], metric_kind="error_rate")
    assert found is not None
    assert found.method == "percentile"


async def test_scan_persists_and_scopes_to_data_source(session, seeded_demo):
    anomalies = await scan(session, data_source=DataSource.DEMO.value, window_minutes=90)
    assert all(a.data_source == DataSource.DEMO.value for a in anomalies)


async def test_scan_on_empty_production_finds_nothing(session):
    assert await scan(session, data_source=DataSource.PRODUCTION.value) == []
