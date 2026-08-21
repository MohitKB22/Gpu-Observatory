"""Deterministic diagnostics engine.

These tests assert the engine reaches the right conclusion from telemetry it
has actually observed, for every scenario the specification lists.
"""

import pytest

from app.core.timerange import resolve_range
from app.demo.runner import backfill, reset_demo_data
from app.models.enums import DataSource
from app.services.diagnostics import diagnose
from app.services.diagnostics.rules import ALL_RULES

# scenario -> the diagnosis kinds that would be a correct primary conclusion
EXPECTED = {
    "healthy": {"healthy"},
    "under_batching": {"under_batching"},
    "vram_pressure": {"vram_saturation"},
    "cpu_bottleneck": {"cpu_bottleneck"},
    "latency_spike": {"latency_spike"},
    "throughput_degradation": {"throughput_degradation"},
    "thermal_throttling": {"thermal_throttling"},
}


def test_all_fifteen_rules_are_registered():
    assert len(ALL_RULES) == 15
    names = {name for name, _ in ALL_RULES}
    for expected in (
        "gpu_under_utilization",
        "vram_saturation",
        "cpu_bottleneck",
        "memory_bottleneck",
        "latency_spike",
        "throughput_degradation",
        "excessive_queueing",
        "under_batching",
        "over_batching",
        "thermal_throttling",
        "power_limitation",
        "high_error_rate",
        "model_regression",
        "abnormal_token_throughput",
        "cost_spike",
    ):
        assert expected in names


@pytest.mark.parametrize("scenario", sorted(EXPECTED))
async def test_engine_identifies_each_scenario(session, scenario):
    await reset_demo_data(session)
    await backfill(session, minutes=40, scenario=scenario, step_seconds=60)

    findings, _ = await diagnose(
        session,
        time_range=resolve_range("1h"),
        data_source=DataSource.DEMO.value,
        persist_results=False,
    )
    assert findings, f"no findings for {scenario}"
    assert findings[0].kind in EXPECTED[scenario], (
        f"{scenario}: expected one of {EXPECTED[scenario]}, " f"got {[f.kind for f in findings]}"
    )


async def test_findings_carry_evidence_and_metrics(session, seeded_demo):
    findings, _ = await diagnose(
        session,
        time_range=resolve_range("1h"),
        data_source=DataSource.DEMO.value,
        persist_results=False,
    )
    top = findings[0]
    assert top.evidence, "a diagnosis must cite its evidence"
    assert top.metrics, "a diagnosis must expose the metrics it fired on"
    assert top.recommendations
    assert 0.0 < top.confidence <= 0.97, "confidence must never be a certainty"
    assert top.root_cause


async def test_diagnosis_matches_the_specified_output_contract(session, seeded_demo):
    findings, _ = await diagnose(
        session,
        time_range=resolve_range("1h"),
        data_source=DataSource.DEMO.value,
        persist_results=False,
    )
    payload = findings[0].model_dump()
    for field in (
        "title",
        "severity",
        "root_cause",
        "evidence",
        "metrics",
        "impact",
        "recommendations",
        "confidence",
        "generated_at",
    ):
        assert field in payload
    assert payload["severity"] in {"info", "low", "medium", "high", "critical"}


async def test_empty_window_yields_an_honest_no_data_result(session):
    findings, _ = await diagnose(
        session,
        time_range=resolve_range("1h"),
        data_source=DataSource.PRODUCTION.value,
        persist_results=False,
    )
    assert len(findings) == 1
    assert findings[0].kind == "healthy"
    assert "no telemetry" in findings[0].title.lower()
    # It must not claim health it cannot observe.
    assert findings[0].confidence < 0.5


async def test_under_batching_supersedes_generic_under_utilisation(session):
    """The specific cause should replace the general symptom, not duplicate it."""
    await reset_demo_data(session)
    await backfill(session, minutes=40, scenario="under_batching", step_seconds=60)
    findings, _ = await diagnose(
        session,
        time_range=resolve_range("1h"),
        data_source=DataSource.DEMO.value,
        persist_results=False,
    )
    kinds = [f.kind for f in findings]
    assert "under_batching" in kinds
    assert "gpu_under_utilization" not in kinds


async def test_multi_gpu_findings_are_coalesced(session):
    await reset_demo_data(session)
    await backfill(session, minutes=40, scenario="thermal_throttling", step_seconds=60)
    findings, _ = await diagnose(
        session,
        time_range=resolve_range("1h"),
        data_source=DataSource.DEMO.value,
        persist_results=False,
    )
    thermal = [f for f in findings if f.kind == "thermal_throttling"]
    assert len(thermal) == 1, "the same issue across devices must report once"
    assert thermal[0].metrics.get("affected_entity_count", 1) >= 1


async def test_diagnoses_persist_and_are_retrievable(session, seeded_demo):
    from sqlalchemy import func, select

    from app.models.analytics import Diagnosis

    await diagnose(
        session,
        time_range=resolve_range("1h"),
        data_source=DataSource.DEMO.value,
        persist_results=True,
    )
    stored = await session.scalar(select(func.count()).select_from(Diagnosis))
    assert stored > 0


async def test_demo_diagnoses_never_leak_into_production(session, seeded_demo):
    from sqlalchemy import select

    from app.models.analytics import Diagnosis

    await diagnose(
        session,
        time_range=resolve_range("1h"),
        data_source=DataSource.DEMO.value,
        persist_results=True,
    )
    rows = list((await session.execute(select(Diagnosis))).scalars().all())
    assert rows
    assert all(r.data_source == DataSource.DEMO.value for r in rows)
