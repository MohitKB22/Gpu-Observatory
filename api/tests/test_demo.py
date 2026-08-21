"""Demo Mode generation and namespace isolation."""

import pytest
from sqlalchemy import func, select

from app.demo.generator import DemoTelemetryGenerator
from app.demo.scenarios import SCENARIOS
from app.models.enums import DataSource
from app.models.inference import InferenceRequest
from app.models.telemetry import Gpu, GpuMetric


def test_all_seven_scenarios_exist():
    assert len(SCENARIOS) == 7
    for key in (
        "healthy",
        "under_batching",
        "vram_pressure",
        "cpu_bottleneck",
        "latency_spike",
        "throughput_degradation",
        "thermal_throttling",
    ):
        assert key in SCENARIOS


def test_generator_is_deterministic_for_a_seed():
    a = DemoTelemetryGenerator("healthy", gpu_count=2, seed=7)
    b = DemoTelemetryGenerator("healthy", gpu_count=2, seed=7)
    a.advance()
    b.advance()
    assert [s.utilization_pct for s in a.gpu_samples()] == [
        s.utilization_pct for s in b.gpu_samples()
    ]


def test_generator_respects_gpu_count():
    generator = DemoTelemetryGenerator("healthy", gpu_count=8)
    assert len(generator.gpu_samples()) == 8
    assert {s.index for s in generator.gpu_samples()} == set(range(8))


def test_demo_devices_are_labelled_simulated():
    """A screenshot must never be mistaken for real hardware inventory."""
    generator = DemoTelemetryGenerator("healthy", gpu_count=1)
    assert "simulated" in generator.device_info()[0].name.lower()
    assert "simulated" in generator.device_info()[0].driver_version.lower()


def test_scenario_signals_are_physically_coherent():
    under = DemoTelemetryGenerator("under_batching", gpu_count=1, seed=1)
    healthy = DemoTelemetryGenerator("healthy", gpu_count=1, seed=1)
    under.advance()
    healthy.advance()
    # Under-batching must depress utilisation and batch size together.
    assert under.gpu_samples()[0].utilization_pct < healthy.gpu_samples()[0].utilization_pct
    assert under.batch_snapshot()["avg_batch_size"] < healthy.batch_snapshot()["avg_batch_size"]


def test_vram_pressure_saturates_memory():
    generator = DemoTelemetryGenerator("vram_pressure", gpu_count=1, seed=3)
    generator.advance()
    assert generator.gpu_samples()[0].memory_utilization_pct > 90


def test_thermal_scenario_reports_throttle_reasons():
    generator = DemoTelemetryGenerator("thermal_throttling", gpu_count=1, seed=3)
    generator.advance()
    sample = generator.gpu_samples()[0]
    assert sample.temperature_c > 80
    assert any("thermal" in r for r in sample.throttle_reasons)


def test_latency_percentiles_have_a_realistic_tail():
    generator = DemoTelemetryGenerator("healthy", gpu_count=1, seed=5)
    generator.advance()
    latencies = sorted(r["total_latency_ms"] for r in generator.inference_requests(seconds=60))
    p50 = latencies[len(latencies) // 2]
    p99 = latencies[int(len(latencies) * 0.99)]
    assert p99 > p50  # a real distribution, not a flat line


def test_unknown_scenario_is_rejected():
    generator = DemoTelemetryGenerator("healthy")
    with pytest.raises(ValueError):
        generator.set_scenario("not-a-real-scenario")


async def test_backfill_writes_only_into_the_demo_namespace(session, seeded_demo):
    """The core integrity guarantee: demo data never lands in production."""
    demo_gpus = await session.scalar(
        select(func.count()).select_from(Gpu).where(Gpu.data_source == DataSource.DEMO.value)
    )
    production_gpus = await session.scalar(
        select(func.count()).select_from(Gpu).where(Gpu.data_source == DataSource.PRODUCTION.value)
    )
    assert demo_gpus > 0
    assert production_gpus == 0

    production_metrics = await session.scalar(
        select(func.count())
        .select_from(GpuMetric)
        .where(GpuMetric.data_source == DataSource.PRODUCTION.value)
    )
    production_requests = await session.scalar(
        select(func.count())
        .select_from(InferenceRequest)
        .where(InferenceRequest.data_source == DataSource.PRODUCTION.value)
    )
    assert production_metrics == 0
    assert production_requests == 0


async def test_reset_clears_demo_but_not_production(session, seeded_demo):
    from app.demo.runner import reset_demo_data
    from app.models.telemetry import Gpu as GpuModel

    session.add(
        GpuModel(
            uuid="GPU-REAL-0001",
            index=0,
            name="Real GPU",
            data_source=DataSource.PRODUCTION.value,
        )
    )
    await session.commit()

    await reset_demo_data(session)

    remaining_demo = await session.scalar(
        select(func.count())
        .select_from(GpuModel)
        .where(GpuModel.data_source == DataSource.DEMO.value)
    )
    remaining_production = await session.scalar(
        select(func.count())
        .select_from(GpuModel)
        .where(GpuModel.data_source == DataSource.PRODUCTION.value)
    )
    assert remaining_demo == 0
    assert remaining_production == 1
