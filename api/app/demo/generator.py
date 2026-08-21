"""Demo Mode telemetry generator.

Produces coherent synthetic GPU, system, inference and batch telemetry for the
selected scenario. Everything it writes is tagged ``data_source='demo'``.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

from app.collectors.base import GpuDeviceInfo, GpuProcessSample, GpuSample, SystemSample
from app.demo.scenarios import (
    SCENARIOS,
    DemoGpuSpec,
    ScenarioProfile,
    build_demo_gpus,
    clamp,
    diurnal_factor,
    jitter,
    scenario_or_default,
)
from app.models.enums import DemoScenario


class DemoTelemetryGenerator:
    """Deterministic-by-seed generator for demo telemetry."""

    #: Ticks over which a ramped scenario completes one full cycle.
    CYCLE_TICKS = 60
    #: Upper bound on synthesised request rate, as a safety valve only.
    MAX_DEMO_RPS = 60

    def __init__(
        self,
        scenario: str = DemoScenario.HEALTHY.value,
        gpu_count: int = 4,
        seed: int | None = None,
    ) -> None:
        self.scenario_key = scenario if scenario in SCENARIOS else DemoScenario.HEALTHY.value
        self.gpus: list[DemoGpuSpec] = build_demo_gpus(gpu_count)
        self._rng = random.Random(seed if seed is not None else 20240613)
        self._tick = 0

    # ------------------------------------------------------------ control ---
    @property
    def profile(self) -> ScenarioProfile:
        return scenario_or_default(self.scenario_key)

    def set_scenario(self, scenario: str) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown demo scenario: {scenario}")
        self.scenario_key = scenario
        self._tick = 0

    @property
    def tick(self) -> int:
        return self._tick

    @property
    def progress(self) -> float:
        """Position within the scenario cycle, in [0, 1].

        Ramped scenarios use this so a 'latency spike' actually rises across
        the window instead of sitting flat at an elevated value.
        """
        return (self._tick % self.CYCLE_TICKS) / self.CYCLE_TICKS

    def advance(self) -> None:
        self._tick += 1

    # ------------------------------------------------------------ devices ---
    def device_info(self) -> list[GpuDeviceInfo]:
        return [
            GpuDeviceInfo(
                uuid=spec.uuid,
                index=spec.index,
                name=spec.name,
                driver_version=spec.driver_version,
                cuda_version=spec.cuda_version,
                vbios_version="96.00.89.00.01 (simulated)",
                serial=f"DEMO{spec.index:08d}",
                total_memory_mb=spec.total_memory_mb,
                power_limit_w=spec.power_limit_w,
                max_clock_mhz=spec.max_clock_mhz,
                max_memory_clock_mhz=spec.max_memory_clock_mhz,
                compute_capability=spec.compute_capability,
                pcie_gen=spec.pcie_gen,
                pcie_width=spec.pcie_width,
            )
            for spec in self.gpus
        ]

    # ------------------------------------------------------------ samples ---
    def gpu_samples(self, at: datetime | None = None) -> list[GpuSample]:
        profile = self.profile
        moment = at or datetime.now(timezone.utc)
        curve = diurnal_factor(self._tick)
        util_ramp = max(0.08, 1.0 + profile.gpu_util_ramp * self.progress)
        temp_ramp = max(0.08, 1.0 + profile.temperature_ramp * self.progress)
        samples: list[GpuSample] = []

        for spec in self.gpus:
            # Give each device a stable personality so they are not clones.
            device_bias = 1.0 + ((spec.index % 4) - 1.5) * 0.045

            util = clamp(
                jitter(
                    profile.gpu_utilization * curve * device_bias * util_ramp,
                    profile.gpu_utilization_jitter,
                    self._rng,
                ),
                0.0,
                100.0,
            )
            vram_pct = clamp(
                jitter(profile.vram_utilization * device_bias, 2.2, self._rng), 0.5, 99.9
            )
            used_mb = spec.total_memory_mb * vram_pct / 100.0
            temperature = clamp(
                jitter(profile.temperature_c * device_bias * temp_ramp, 1.6, self._rng), 20.0, 95.0
            )
            power = clamp(
                jitter(spec.power_limit_w * profile.power_fraction * device_bias, 14.0, self._rng),
                40.0,
                spec.power_limit_w,
            )
            sm_clock = int(
                clamp(
                    jitter(spec.max_clock_mhz * profile.sm_clock_fraction, 28.0, self._rng),
                    210.0,
                    float(spec.max_clock_mhz),
                )
            )

            throttle: list[str] = []
            if profile.throttled:
                throttle = ["hw_thermal_slowdown", "sw_thermal_slowdown"]
            elif power > spec.power_limit_w * 0.97:
                throttle = ["sw_power_cap"]

            processes = [
                GpuProcessSample(
                    pid=4100 + spec.index * 10 + i,
                    process_name=name,
                    used_memory_mb=round(used_mb * share, 1),
                    sm_utilization_pct=round(clamp(util * share * 1.6, 0, 100), 1),
                    workload_label=f"demo-{name}",
                )
                for i, (name, share) in enumerate(
                    zip(spec.processes, (0.62, 0.26, 0.08), strict=False)
                )
            ]

            samples.append(
                GpuSample(
                    uuid=spec.uuid,
                    index=spec.index,
                    recorded_at=moment,
                    utilization_pct=round(util, 2),
                    memory_utilization_pct=round(vram_pct, 2),
                    memory_used_mb=round(used_mb, 1),
                    memory_free_mb=round(spec.total_memory_mb - used_mb, 1),
                    memory_total_mb=spec.total_memory_mb,
                    temperature_c=round(temperature, 1),
                    power_w=round(power, 1),
                    power_limit_w=spec.power_limit_w,
                    sm_clock_mhz=sm_clock,
                    memory_clock_mhz=spec.max_memory_clock_mhz,
                    fan_speed_pct=round(clamp((temperature - 30) * 2.1, 0, 100), 1),
                    pcie_tx_kb_s=round(jitter(920_000 * (util / 100), 40_000, self._rng), 1),
                    pcie_rx_kb_s=round(jitter(760_000 * (util / 100), 35_000, self._rng), 1),
                    throttle_reasons=throttle,
                    ecc_errors=0,
                    processes=processes,
                )
            )
        return samples

    def system_sample(self, at: datetime | None = None, host: str = "demo-node-01") -> SystemSample:
        profile = self.profile
        moment = at or datetime.now(timezone.utc)
        curve = diurnal_factor(self._tick)
        cores = 64

        cpu = clamp(jitter(profile.cpu_utilization * curve, 3.4, self._rng), 0.0, 100.0)
        ram_pct = clamp(jitter(profile.ram_utilization, 2.0, self._rng), 1.0, 99.0)
        ram_total = 512 * 1024.0

        return SystemSample(
            recorded_at=moment,
            host=host,
            cpu_utilization_pct=round(cpu, 2),
            per_core_utilization=[
                round(clamp(jitter(cpu, 12.0, self._rng), 0, 100), 1) for _ in range(cores)
            ],
            core_count=cores,
            load_avg_1m=round(cores * cpu / 100 * 0.9, 2),
            load_avg_5m=round(cores * cpu / 100 * 0.82, 2),
            load_avg_15m=round(cores * cpu / 100 * 0.74, 2),
            ram_total_mb=ram_total,
            ram_used_mb=round(ram_total * ram_pct / 100, 1),
            ram_utilization_pct=round(ram_pct, 2),
            swap_total_mb=8192.0,
            swap_used_mb=round(clamp(jitter(120, 40, self._rng), 0, 8192), 1),
            disk_total_gb=7500.0,
            disk_used_gb=round(jitter(3120, 8, self._rng), 1),
            disk_utilization_pct=round(jitter(41.6, 0.4, self._rng), 2),
            net_sent_kb_s=round(jitter(148_000 * (cpu / 100), 6_000, self._rng), 1),
            net_recv_kb_s=round(jitter(121_000 * (cpu / 100), 5_000, self._rng), 1),
            process_count=int(jitter(742, 22, self._rng)),
        )

    # ---------------------------------------------------------- inference ---
    def inference_requests(
        self,
        at: datetime | None = None,
        seconds: float = 5.0,
        max_requests: int | None = None,
    ) -> list[dict]:
        """Generate individual request records for the elapsed interval.

        Latency is drawn from a log-normal-ish shape so percentiles behave the
        way real serving traffic does (a long right tail, not a flat spread).
        """
        profile = self.profile
        moment = at or datetime.now(timezone.utc)
        curve = diurnal_factor(self._tick)

        throughput_ramp = max(0.08, 1.0 + profile.throughput_ramp * self.progress)
        latency_ramp = max(0.08, 1.0 + profile.latency_ramp * self.progress)
        # The safety cap scales with the interval so it never truncates the
        # request stream and flattens the throughput signal.
        cap = max_requests if max_requests is not None else int(seconds * self.MAX_DEMO_RPS)
        expected = profile.throughput_rps * seconds * curve * throughput_ramp
        count = min(cap, max(1, int(jitter(expected, expected * 0.08, self._rng))))

        requests: list[dict] = []
        for i in range(count):
            offset = seconds * (i / count)
            started = moment - timedelta(seconds=seconds - offset)

            base = profile.base_latency_ms * latency_ramp
            spread = profile.latency_spread
            # Log-normal tail.
            latency = base * math.exp(self._rng.gauss(0.0, spread))
            # Occasional genuine outliers, more likely in unhealthy scenarios.
            if self._rng.random() < (0.02 + spread * 0.04):
                latency *= self._rng.uniform(1.8, 3.6)

            queue = max(
                0.0, jitter(profile.queue_latency_ms, profile.queue_latency_ms * 0.5, self._rng)
            )
            preprocess = max(0.1, jitter(base * 0.06, base * 0.02, self._rng))
            postprocess = max(0.1, jitter(base * 0.04, base * 0.015, self._rng))
            execution = max(0.5, latency - queue - preprocess - postprocess)

            batch = max(
                1,
                int(
                    round(jitter(profile.avg_batch_size, profile.avg_batch_size * 0.35, self._rng))
                ),
            )
            batch = min(batch, profile.configured_max_batch)
            input_tokens = max(1, int(jitter(profile.tokens_per_request * 0.62, 40, self._rng)))
            output_tokens = max(1, int(jitter(profile.tokens_per_request * 0.38, 26, self._rng)))
            is_error = self._rng.random() < profile.error_rate

            requests.append(
                {
                    "started_at": started,
                    "total_latency_ms": round(latency + queue, 3),
                    "queue_latency_ms": round(queue, 3),
                    "preprocess_latency_ms": round(preprocess, 3),
                    "execution_latency_ms": round(execution, 3),
                    "postprocess_latency_ms": round(postprocess, 3),
                    "time_to_first_token_ms": round(queue + preprocess + execution * 0.22, 3),
                    "input_tokens": input_tokens,
                    "output_tokens": 0 if is_error else output_tokens,
                    "batch_size": batch,
                    "concurrency": max(
                        1, int(jitter(profile.throughput_rps * base / 1000, 3, self._rng))
                    ),
                    "status_code": 503 if is_error else 200,
                    "is_error": is_error,
                    "error_type": "backend_overloaded" if is_error else None,
                }
            )
        return requests

    def batch_snapshot(self) -> dict:
        """Aggregate batching state for the current tick."""
        profile = self.profile
        avg_batch = max(
            1.0, jitter(profile.avg_batch_size, profile.avg_batch_size * 0.12, self._rng)
        )
        efficiency = clamp(avg_batch / profile.configured_max_batch, 0.0, 1.0)
        return {
            "requested_batch_size": float(profile.configured_max_batch),
            "effective_batch_size": round(avg_batch, 2),
            "avg_batch_size": round(avg_batch, 2),
            "max_batch_size": int(min(profile.configured_max_batch, round(avg_batch * 1.7))),
            "configured_max_batch_size": profile.configured_max_batch,
            "queue_depth": round(
                max(0.0, jitter(profile.queue_latency_ms * 0.6, 1.2, self._rng)), 2
            ),
            "batch_formation_ms": round(
                max(0.1, jitter(profile.queue_latency_ms * 0.8, 1.0, self._rng)), 2
            ),
            "batch_efficiency": round(efficiency, 4),
            "gpu_utilization_pct": round(
                clamp(
                    jitter(
                        profile.gpu_utilization
                        * max(0.08, 1.0 + profile.gpu_util_ramp * self.progress),
                        3.0,
                        self._rng,
                    ),
                    0,
                    100,
                ),
                2,
            ),
            "throughput_rps": round(
                max(
                    0.0,
                    jitter(
                        profile.throughput_rps * (1.0 + profile.throughput_ramp * self.progress),
                        profile.throughput_rps * 0.06,
                        self._rng,
                    ),
                ),
                2,
            ),
        }
