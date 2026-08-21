"""Demo Mode scenario definitions.

Demo telemetry is synthetic. It is written exclusively with
``data_source='demo'`` and every read path filters on that discriminator, so
synthetic data can never be presented as production telemetry.

Each scenario produces a physically coherent signal set so the diagnostics
engine has something real to reason about: an under-batching scenario really
does depress batch size and GPU utilisation together, rather than randomising
independent numbers.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from app.models.enums import DemoScenario


@dataclass(frozen=True)
class ScenarioProfile:
    """Target operating point for a scenario."""

    key: str
    title: str
    description: str
    expected_diagnosis: str

    gpu_utilization: float
    gpu_utilization_jitter: float = 4.0
    vram_utilization: float = 55.0
    temperature_c: float = 62.0
    power_fraction: float = 0.62
    sm_clock_fraction: float = 0.95

    cpu_utilization: float = 35.0
    ram_utilization: float = 45.0

    base_latency_ms: float = 85.0
    latency_spread: float = 0.28
    queue_latency_ms: float = 4.0
    throughput_rps: float = 15.0
    avg_batch_size: float = 16.0
    configured_max_batch: int = 32
    error_rate: float = 0.004
    tokens_per_request: int = 220
    throttled: bool = False
    # Fractional drift applied across the scenario cycle so 'spike' and
    # 'degradation' scenarios genuinely change over time rather than
    # sitting at a constant elevated level.
    latency_ramp: float = 0.0
    throughput_ramp: float = 0.0
    gpu_util_ramp: float = 0.0
    temperature_ramp: float = 0.0


SCENARIOS: dict[str, ScenarioProfile] = {
    DemoScenario.HEALTHY.value: ScenarioProfile(
        key=DemoScenario.HEALTHY.value,
        title="Healthy GPU",
        description=(
            "Well-tuned serving: high GPU utilisation, batches near the "
            "configured maximum, stable latency and negligible errors."
        ),
        expected_diagnosis="healthy",
        gpu_utilization=88.0,
        vram_utilization=68.0,
        temperature_c=68.0,
        power_fraction=0.82,
        cpu_utilization=38.0,
        base_latency_ms=78.0,
        latency_spread=0.18,
        queue_latency_ms=3.0,
        throughput_rps=20.0,
        avg_batch_size=27.0,
        error_rate=0.002,
    ),
    DemoScenario.UNDER_BATCHING.value: ScenarioProfile(
        key=DemoScenario.UNDER_BATCHING.value,
        title="Under-batching",
        description=(
            "Request volume is healthy but batches form far below the "
            "configured maximum, leaving the GPU idle between small kernels."
        ),
        expected_diagnosis="under_batching",
        gpu_utilization=31.0,
        gpu_utilization_jitter=5.0,
        vram_utilization=34.0,
        temperature_c=54.0,
        power_fraction=0.36,
        cpu_utilization=42.0,
        base_latency_ms=96.0,
        latency_spread=0.22,
        queue_latency_ms=1.5,
        throughput_rps=11.0,
        avg_batch_size=2.2,
        configured_max_batch=32,
        error_rate=0.003,
    ),
    DemoScenario.VRAM_PRESSURE.value: ScenarioProfile(
        key=DemoScenario.VRAM_PRESSURE.value,
        title="VRAM pressure",
        description=(
            "KV-cache growth pushes VRAM near capacity; the scheduler preempts "
            "sequences and tail latency climbs."
        ),
        expected_diagnosis="vram_saturation",
        gpu_utilization=79.0,
        vram_utilization=96.5,
        temperature_c=72.0,
        power_fraction=0.79,
        cpu_utilization=40.0,
        base_latency_ms=168.0,
        latency_spread=0.55,
        queue_latency_ms=42.0,
        throughput_rps=10.0,
        avg_batch_size=9.0,
        error_rate=0.021,
    ),
    DemoScenario.CPU_BOTTLENECK.value: ScenarioProfile(
        key=DemoScenario.CPU_BOTTLENECK.value,
        title="CPU bottleneck",
        description=(
            "Tokenisation and pre/post-processing saturate the host CPU, so the "
            "GPU waits on input despite ample capacity."
        ),
        expected_diagnosis="cpu_bottleneck",
        gpu_utilization=37.0,
        vram_utilization=44.0,
        temperature_c=56.0,
        power_fraction=0.40,
        cpu_utilization=96.0,
        ram_utilization=71.0,
        base_latency_ms=142.0,
        latency_spread=0.34,
        queue_latency_ms=38.0,
        throughput_rps=9.0,
        avg_batch_size=11.0,
        error_rate=0.005,
    ),
    DemoScenario.LATENCY_SPIKE.value: ScenarioProfile(
        key=DemoScenario.LATENCY_SPIKE.value,
        title="Latency spike",
        description=(
            "A burst of long-context requests inflates the tail: P99 separates "
            "sharply from the median while throughput sags."
        ),
        expected_diagnosis="latency_spike",
        gpu_utilization=74.0,
        vram_utilization=71.0,
        temperature_c=70.0,
        power_fraction=0.75,
        cpu_utilization=52.0,
        base_latency_ms=310.0,
        latency_spread=0.95,
        queue_latency_ms=88.0,
        throughput_rps=8.0,
        avg_batch_size=13.0,
        error_rate=0.014,
        latency_ramp=3.2,
        throughput_ramp=-0.45,
    ),
    DemoScenario.THROUGHPUT_DEGRADATION.value: ScenarioProfile(
        key=DemoScenario.THROUGHPUT_DEGRADATION.value,
        title="Throughput degradation",
        description=(
            "Sustained decline in completed requests and tokens per second "
            "without a corresponding drop in offered load."
        ),
        expected_diagnosis="throughput_degradation",
        gpu_utilization=58.0,
        vram_utilization=63.0,
        temperature_c=66.0,
        power_fraction=0.58,
        cpu_utilization=47.0,
        base_latency_ms=155.0,
        latency_spread=0.40,
        queue_latency_ms=52.0,
        throughput_rps=5.0,
        avg_batch_size=7.5,
        error_rate=0.012,
        tokens_per_request=180,
        throughput_ramp=-1.15,
        latency_ramp=0.55,
        gpu_util_ramp=-0.3,
    ),
    DemoScenario.THERMAL_THROTTLING.value: ScenarioProfile(
        key=DemoScenario.THERMAL_THROTTLING.value,
        title="Thermal throttling",
        description=(
            "The device exceeds its thermal limit, clocks are cut by the "
            "hardware slowdown path, and effective throughput falls."
        ),
        expected_diagnosis="thermal_throttling",
        gpu_utilization=81.0,
        vram_utilization=66.0,
        temperature_c=87.5,
        power_fraction=0.97,
        sm_clock_fraction=0.62,
        cpu_utilization=44.0,
        base_latency_ms=134.0,
        latency_spread=0.33,
        queue_latency_ms=26.0,
        throughput_rps=9.0,
        avg_batch_size=14.0,
        error_rate=0.006,
        throttled=True,
        temperature_ramp=0.09,
    ),
}


@dataclass
class DemoGpuSpec:
    """Static description of a simulated device.

    The name is deliberately marked as simulated so a screenshot can never be
    mistaken for real hardware inventory.
    """

    index: int
    uuid: str
    name: str = "NVIDIA H100 80GB HBM3 (simulated)"
    total_memory_mb: float = 81_559.0
    power_limit_w: float = 700.0
    max_clock_mhz: int = 1980
    max_memory_clock_mhz: int = 2619
    compute_capability: str = "9.0"
    driver_version: str = "550.90.07 (simulated)"
    cuda_version: str = "12.4"
    pcie_gen: int = 5
    pcie_width: int = 16
    processes: list[str] = field(
        default_factory=lambda: ["vllm-worker", "triton-server", "tokenizer-pool"]
    )


def build_demo_gpus(count: int) -> list[DemoGpuSpec]:
    return [
        DemoGpuSpec(index=i, uuid=f"GPU-DEMO-{i:04d}-0000-0000-000000000000")
        for i in range(max(1, count))
    ]


def scenario_or_default(key: str | None) -> ScenarioProfile:
    return SCENARIOS.get(key or "", SCENARIOS[DemoScenario.HEALTHY.value])


def diurnal_factor(tick: int, period: int = 240) -> float:
    """A slow sinusoidal load curve so charts are not flat lines."""
    return 1.0 + 0.12 * math.sin(2 * math.pi * (tick % period) / period)


def jitter(value: float, spread: float, rng: random.Random) -> float:
    return value + rng.uniform(-spread, spread)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
