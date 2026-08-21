"""The fifteen deterministic diagnostic rules.

Every rule is a pure function of :class:`DiagnosticContext`. A rule returns a
:class:`Finding` only when its evidence threshold is met, and every returned
finding carries the concrete numbers it fired on -- nothing is asserted that
cannot be traced back to a stored measurement.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from app.models.enums import DiagnosisKind, Severity
from app.services.diagnostics.context import DiagnosticContext

# Thresholds are named so the reasoning is legible rather than magic numbers.
GPU_IDLE_PCT = 55.0
GPU_UTIL_DROP_PCT = -15.0
VRAM_SATURATION_PCT = 92.0
VRAM_CRITICAL_PCT = 97.0
CPU_SATURATION_PCT = 85.0
RAM_SATURATION_PCT = 90.0
LATENCY_SPIKE_PCT = 35.0
THROUGHPUT_DROP_PCT = -20.0
QUEUE_DOMINANCE_RATIO = 0.30
BATCH_EFFICIENCY_LOW = 0.35
BATCH_EFFICIENCY_HIGH = 0.95
QUEUE_DEPTH_HIGH = 8.0
THERMAL_LIMIT_C = 83.0
POWER_LIMIT_RATIO = 0.97
ERROR_RATE_HIGH = 0.02
TOKEN_DROP_PCT = -25.0
COST_SPIKE_PCT = 30.0
TAIL_RATIO_HIGH = 4.0


@dataclass
class Finding:
    """One diagnostic conclusion with its supporting evidence."""

    kind: str
    title: str
    severity: str
    root_cause: str
    evidence: list[str] = field(default_factory=list)
    metrics: dict[str, float | int | str | None] = field(default_factory=dict)
    impact: str | None = None
    recommendations: list[str] = field(default_factory=list)
    confidence: float = 0.0
    entity_type: str | None = None
    entity_id: str | None = None
    entity_label: str | None = None


Rule = Callable[[DiagnosticContext], list[Finding]]


def _fmt(value: float | None, unit: str = "", digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}{unit}"


def _confidence(signals: list[bool], base: float = 0.45, step: float = 0.12) -> float:
    """Confidence grows with the number of corroborating signals, capped at 0.97.

    Deliberately never returns 1.0: these are inferences from telemetry, not
    proofs.
    """
    return round(min(0.97, base + step * sum(1 for s in signals if s)), 2)


# --------------------------------------------------------------- 1. GPU idle --
def rule_gpu_under_utilization(ctx: DiagnosticContext) -> list[Finding]:
    findings: list[Finding] = []
    for gpu in ctx.gpus:
        avg = gpu.utilization.avg
        if avg is None or gpu.utilization.count < 3:
            continue
        change = gpu.utilization.change_pct
        dropped = change is not None and change <= GPU_UTIL_DROP_PCT
        idle = avg < GPU_IDLE_PCT
        if not idle and not dropped:
            continue
        # Only meaningful if there is actually work to do.
        if not ctx.has_inference_data or ctx.request_count == 0:
            continue

        evidence = [
            f"{gpu.label} averaged {_fmt(avg, '%')} utilisation over the window.",
            f"{ctx.request_count} inference requests were served in the same "
            "window, so the device was not idle for lack of traffic.",
        ]
        if dropped and change is not None:
            evidence.append(
                f"Utilisation fell {abs(change):.1f}% between the first and second "
                f"half of the window ({_fmt(gpu.utilization.first_half_avg, '%')} → "
                f"{_fmt(gpu.utilization.second_half_avg, '%')})."
            )
        batch_avg = ctx.batch_size.avg
        if batch_avg is not None and ctx.configured_max_batch:
            evidence.append(
                f"Average batch size was {batch_avg:.1f} against a configured "
                f"maximum of {ctx.configured_max_batch}."
            )

        severity = Severity.HIGH.value if avg < 30 else Severity.MEDIUM.value
        findings.append(
            Finding(
                kind=DiagnosisKind.GPU_UNDER_UTILIZATION.value,
                title=f"GPU under-utilisation detected on {gpu.label}",
                severity=severity,
                root_cause=(
                    "The GPU is spending a significant fraction of the window idle "
                    "while inference traffic is present, indicating the device is "
                    "starved of work rather than saturated."
                ),
                evidence=evidence,
                metrics={
                    "gpu_utilization_avg_pct": round(avg, 2),
                    "gpu_utilization_change_pct": round(change, 2) if change is not None else None,
                    "request_count": ctx.request_count,
                    "avg_batch_size": round(batch_avg, 2) if batch_avg is not None else None,
                    "configured_max_batch_size": ctx.configured_max_batch,
                },
                impact=(
                    f"Roughly {max(0.0, 100 - avg):.0f}% of paid GPU capacity is not "
                    "being converted into throughput."
                ),
                recommendations=[
                    "Increase the dynamic batching window so more requests "
                    "coalesce per kernel launch.",
                    "Raise the maximum batch size if VRAM headroom allows.",
                    "Verify the client is issuing requests concurrently rather than serially.",
                    "Consider consolidating this workload onto fewer GPUs.",
                ],
                confidence=_confidence(
                    [idle, dropped, batch_avg is not None, ctx.request_count > 100]
                ),
                entity_type="gpu",
                entity_id=gpu.gpu_id,
                entity_label=gpu.label,
            )
        )
    return findings


# ---------------------------------------------------------- 2. VRAM pressure --
def rule_vram_saturation(ctx: DiagnosticContext) -> list[Finding]:
    findings: list[Finding] = []
    for gpu in ctx.gpus:
        peak = gpu.vram_pct.peak
        avg = gpu.vram_pct.avg
        if peak is None or avg is None:
            continue
        if peak < VRAM_SATURATION_PCT:
            continue

        critical = peak >= VRAM_CRITICAL_PCT
        evidence = [
            f"{gpu.label} peaked at {_fmt(peak, '%')} VRAM utilisation "
            f"(average {_fmt(avg, '%')}).",
        ]
        if gpu.total_memory_mb and gpu.vram_used_mb.peak:
            free = gpu.total_memory_mb - gpu.vram_used_mb.peak
            evidence.append(
                f"Only {_fmt(free, ' MB', 0)} of {_fmt(gpu.total_memory_mb, ' MB', 0)} "
                "remained free at peak."
            )
        error_avg = ctx.error_rate.avg
        if error_avg and error_avg > ERROR_RATE_HIGH:
            evidence.append(
                f"Error rate averaged {error_avg * 100:.2f}%, consistent with "
                "allocation failures or scheduler preemption under memory pressure."
            )
        p99 = ctx.latency_p99.avg
        if p99:
            evidence.append(f"P99 latency averaged {_fmt(p99, ' ms')} during the same window.")

        findings.append(
            Finding(
                kind=DiagnosisKind.VRAM_SATURATION.value,
                title=f"VRAM saturation on {gpu.label}",
                severity=Severity.CRITICAL.value if critical else Severity.HIGH.value,
                root_cause=(
                    "GPU memory is at or near capacity. Once the KV cache cannot grow, "
                    "the scheduler preempts or queues sequences instead of running them, "
                    "which inflates tail latency and can surface as request errors."
                ),
                evidence=evidence,
                metrics={
                    "vram_peak_pct": round(peak, 2),
                    "vram_avg_pct": round(avg, 2),
                    "vram_total_mb": round(gpu.total_memory_mb, 1) if gpu.total_memory_mb else None,
                    "error_rate": round(error_avg, 4) if error_avg is not None else None,
                    "p99_latency_ms": round(p99, 2) if p99 else None,
                },
                impact=(
                    "Requests are being preempted or rejected; tail latency and error "
                    "rate degrade before average latency shows the problem."
                ),
                recommendations=[
                    "Reduce maximum batch size or maximum sequence length to "
                    "bound KV-cache growth.",
                    "Lower the KV-cache memory fraction so the allocator retains headroom.",
                    "Enable or increase quantisation (FP8/INT8) to cut weight and cache footprint.",
                    "Shard the model across additional GPUs with tensor parallelism.",
                ],
                confidence=_confidence(
                    [True, critical, bool(error_avg and error_avg > ERROR_RATE_HIGH), bool(p99)],
                    base=0.55,
                ),
                entity_type="gpu",
                entity_id=gpu.gpu_id,
                entity_label=gpu.label,
            )
        )
    return findings


# --------------------------------------------------------- 3. CPU bottleneck --
def rule_cpu_bottleneck(ctx: DiagnosticContext) -> list[Finding]:
    cpu_avg = ctx.cpu.avg
    if cpu_avg is None or cpu_avg < CPU_SATURATION_PCT:
        return []
    gpu_avg = ctx.avg_gpu_utilization
    gpu_idle = gpu_avg is not None and gpu_avg < GPU_IDLE_PCT

    evidence = [f"Host CPU averaged {_fmt(cpu_avg, '%')} utilisation."]
    if gpu_avg is not None:
        evidence.append(f"GPU utilisation averaged only {_fmt(gpu_avg, '%')} over the same window.")
    queue = ctx.queue_latency.avg
    p95 = ctx.latency_p95.avg
    if queue and p95:
        evidence.append(f"Queue latency averaged {_fmt(queue, ' ms')} of {_fmt(p95, ' ms')} P95.")

    return [
        Finding(
            kind=DiagnosisKind.CPU_BOTTLENECK.value,
            title="Host CPU is bottlenecking the GPU",
            severity=Severity.HIGH.value if gpu_idle else Severity.MEDIUM.value,
            root_cause=(
                "The host CPU is saturated while the GPU has spare capacity. "
                "Tokenisation, request marshalling and pre/post-processing run on the "
                "CPU, so once it saturates the GPU waits on input."
            ),
            evidence=evidence,
            metrics={
                "cpu_utilization_avg_pct": round(cpu_avg, 2),
                "gpu_utilization_avg_pct": round(gpu_avg, 2) if gpu_avg is not None else None,
                "queue_latency_ms": round(queue, 2) if queue else None,
            },
            impact=(
                "GPU throughput is capped by host-side processing; adding GPUs will "
                "not help until the CPU path is relieved."
            ),
            recommendations=[
                "Move tokenisation off the request path or cache tokenised prompts.",
                "Increase API worker processes or dedicate cores to the serving process.",
                "Offload pre/post-processing to a separate service or to the GPU.",
                "Profile the host to confirm which stage dominates CPU time.",
            ],
            confidence=_confidence([True, gpu_idle, bool(queue), ctx.has_inference_data], base=0.5),
            entity_type="host",
            entity_label="host",
        )
    ]


# ------------------------------------------------------ 4. Memory bottleneck --
def rule_memory_bottleneck(ctx: DiagnosticContext) -> list[Finding]:
    ram_avg = ctx.ram.avg
    if ram_avg is None or ram_avg < RAM_SATURATION_PCT:
        return []
    swap = ctx.swap_used.avg
    swapping = bool(swap and swap > 256)

    evidence = [f"Host RAM averaged {_fmt(ram_avg, '%')} utilisation."]
    if swapping:
        evidence.append(
            f"Swap usage averaged {_fmt(swap, ' MB', 0)}, indicating memory exhaustion."
        )

    return [
        Finding(
            kind=DiagnosisKind.MEMORY_BOTTLENECK.value,
            title="Host memory pressure",
            severity=Severity.HIGH.value if swapping else Severity.MEDIUM.value,
            root_cause=(
                "Host system memory is nearly exhausted. Under pressure the kernel "
                "reclaims page cache and may swap, which stalls the serving process "
                "at unpredictable points."
            ),
            evidence=evidence,
            metrics={
                "ram_utilization_avg_pct": round(ram_avg, 2),
                "swap_used_mb": round(swap, 1) if swap else None,
            },
            impact="Latency becomes erratic and the process risks OOM termination.",
            recommendations=[
                "Reduce host-side request buffering and queue depth.",
                "Lower worker process count or per-worker memory limits.",
                "Increase host memory or schedule the workload on a larger node.",
                "Check for memory leaks in pre/post-processing code paths.",
            ],
            confidence=_confidence([True, swapping, ctx.has_system_data], base=0.5),
            entity_type="host",
            entity_label="host",
        )
    ]


# ---------------------------------------------------------- 5. Latency spike --
def rule_latency_spike(ctx: DiagnosticContext) -> list[Finding]:
    change = ctx.latency_p95.change_pct
    p95_avg = ctx.latency_p95.avg
    if p95_avg is None or ctx.latency_p95.count < 4:
        return []
    if change is None or change < LATENCY_SPIKE_PCT:
        return []

    p50 = ctx.latency_p50.avg
    p99 = ctx.latency_p99.avg
    tail_ratio = (p99 / p50) if (p99 and p50) else None
    heavy_tail = bool(tail_ratio and tail_ratio > TAIL_RATIO_HIGH)

    evidence = [
        f"P95 latency rose {change:.1f}% across the window "
        f"({_fmt(ctx.latency_p95.first_half_avg, ' ms')} → "
        f"{_fmt(ctx.latency_p95.second_half_avg, ' ms')}).",
    ]
    if tail_ratio:
        shape = (
            "indicating a heavy tail rather than a uniform slowdown"
            if heavy_tail
            else "a comparatively even distribution"
        )
        evidence.append(
            f"P99/P50 ratio is {tail_ratio:.1f}× "
            f"({_fmt(p99, ' ms')} vs {_fmt(p50, ' ms')}), {shape}."
        )
    throughput_change = ctx.throughput.change_pct
    if throughput_change is not None:
        evidence.append(f"Throughput changed {throughput_change:+.1f}% over the same period.")
    queue = ctx.queue_latency.avg
    if queue and p95_avg:
        evidence.append(f"Queue time accounts for {queue / p95_avg * 100:.0f}% of P95 latency.")

    return [
        Finding(
            kind=DiagnosisKind.LATENCY_SPIKE.value,
            title="Latency spike detected",
            severity=Severity.HIGH.value if change > 80 else Severity.MEDIUM.value,
            root_cause=(
                "Request latency increased materially within the window. "
                + (
                    "The heavy tail points to a subset of expensive requests or "
                    "scheduler preemption rather than a uniform slowdown."
                    if heavy_tail
                    else "The shift is broad-based, suggesting a systemic change "
                    "in serving conditions."
                )
            ),
            evidence=evidence,
            metrics={
                "p95_latency_change_pct": round(change, 2),
                "p95_latency_avg_ms": round(p95_avg, 2),
                "p50_latency_avg_ms": round(p50, 2) if p50 else None,
                "p99_latency_avg_ms": round(p99, 2) if p99 else None,
                "tail_ratio": round(tail_ratio, 2) if tail_ratio else None,
                "queue_latency_ms": round(queue, 2) if queue else None,
            },
            impact="Client-visible response times degraded; SLO burn is likely.",
            recommendations=[
                "Inspect the request-performance table for outlier input lengths.",
                "Check whether VRAM pressure is forcing sequence preemption.",
                "Cap maximum sequence length or route long-context requests separately.",
                "Correlate the spike against deployment and configuration changes.",
            ],
            confidence=_confidence(
                [True, heavy_tail, bool(queue), ctx.latency_p95.count >= 10], base=0.5
            ),
            entity_type="deployment",
        )
    ]


# --------------------------------------------------- 6. Throughput slowdown --
def rule_throughput_degradation(ctx: DiagnosticContext) -> list[Finding]:
    change = ctx.throughput.change_pct
    if change is None or change > THROUGHPUT_DROP_PCT or ctx.throughput.count < 4:
        return []

    concurrency_change = ctx.concurrency.change_pct
    demand_stable = concurrency_change is None or concurrency_change > -10
    error_avg = ctx.error_rate.avg

    evidence = [
        f"Throughput fell {abs(change):.1f}% "
        f"({_fmt(ctx.throughput.first_half_avg, ' req/s', 2)} → "
        f"{_fmt(ctx.throughput.second_half_avg, ' req/s', 2)}).",
    ]
    if concurrency_change is not None:
        evidence.append(
            f"Offered concurrency changed {concurrency_change:+.1f}%, so the decline "
            f"is {'not' if demand_stable else ''} explained by reduced demand."
        )
    if error_avg:
        evidence.append(f"Error rate averaged {error_avg * 100:.2f}%.")

    return [
        Finding(
            kind=DiagnosisKind.THROUGHPUT_DEGRADATION.value,
            title="Throughput degradation",
            severity=Severity.HIGH.value if change < -40 else Severity.MEDIUM.value,
            root_cause=(
                "Completed requests per second declined"
                + (
                    " while offered load held steady, so serving capacity itself regressed."
                    if demand_stable
                    else " alongside a drop in offered load."
                )
            ),
            evidence=evidence,
            metrics={
                "throughput_change_pct": round(change, 2),
                "throughput_avg_rps": round(ctx.throughput.avg, 3) if ctx.throughput.avg else None,
                "concurrency_change_pct": (
                    round(concurrency_change, 2) if concurrency_change is not None else None
                ),
                "error_rate": round(error_avg, 4) if error_avg is not None else None,
            },
            impact="The deployment is serving less traffic per unit of hardware cost.",
            recommendations=[
                "Check for thermal or power throttling on the serving GPUs.",
                "Review batching efficiency and queue depth for scheduler stalls.",
                "Confirm no upstream dependency is rate-limiting the gateway.",
                "Compare against the previous deployment revision for a regression.",
            ],
            confidence=_confidence(
                [True, demand_stable, bool(error_avg), ctx.throughput.count >= 10], base=0.5
            ),
            entity_type="deployment",
        )
    ]


# ---------------------------------------------------- 7. Excessive queueing --
def rule_excessive_queueing(ctx: DiagnosticContext) -> list[Finding]:
    queue = ctx.queue_latency.avg
    p95 = ctx.latency_p95.avg
    if queue is None or p95 is None or p95 <= 0:
        return []
    ratio = queue / p95
    depth = ctx.queue_depth.avg
    if ratio < QUEUE_DOMINANCE_RATIO and (depth is None or depth < QUEUE_DEPTH_HIGH):
        return []

    evidence = [
        f"Queue latency averaged {_fmt(queue, ' ms')}, which is {ratio * 100:.0f}% "
        f"of P95 latency ({_fmt(p95, ' ms')})."
    ]
    if depth is not None:
        evidence.append(f"Average queue depth was {depth:.1f} requests.")
    gpu_avg = ctx.avg_gpu_utilization
    if gpu_avg is not None:
        evidence.append(f"GPU utilisation averaged {_fmt(gpu_avg, '%')} during the same window.")

    saturated = gpu_avg is not None and gpu_avg > 85
    return [
        Finding(
            kind=DiagnosisKind.EXCESSIVE_QUEUEING.value,
            title="Requests are spending excessive time queued",
            severity=Severity.HIGH.value if ratio > 0.5 else Severity.MEDIUM.value,
            root_cause=(
                "A large share of end-to-end latency is queue wait. "
                + (
                    "The GPU is already saturated, so the deployment is capacity-bound."
                    if saturated
                    else "The GPU is not saturated, so the scheduler is holding "
                    "requests rather than admitting them."
                )
            ),
            evidence=evidence,
            metrics={
                "queue_latency_ms": round(queue, 2),
                "p95_latency_ms": round(p95, 2),
                "queue_share_of_p95": round(ratio, 3),
                "queue_depth": round(depth, 2) if depth is not None else None,
                "gpu_utilization_avg_pct": round(gpu_avg, 2) if gpu_avg is not None else None,
            },
            impact="Users wait on admission rather than on computation.",
            recommendations=(
                [
                    "Scale out replicas or add GPUs -- the current capacity is "
                    "genuinely exhausted.",
                    "Apply admission control so excess load fails fast instead of queueing.",
                ]
                if saturated
                else [
                    "Shorten the batch formation window so requests are admitted sooner.",
                    "Raise the scheduler's maximum concurrent sequences.",
                    "Verify no lock or single-threaded stage is serialising admission.",
                ]
            ),
            confidence=_confidence(
                [True, ratio > 0.5, depth is not None, gpu_avg is not None], base=0.5
            ),
            entity_type="deployment",
        )
    ]


# ------------------------------------------------------- 8. Under-batching --
def rule_under_batching(ctx: DiagnosticContext) -> list[Finding]:
    """The flagship rule from specification section 12."""
    batch_avg = ctx.batch_size.avg
    configured = ctx.configured_max_batch
    if batch_avg is None or not configured:
        return []

    efficiency = batch_avg / configured
    if efficiency >= BATCH_EFFICIENCY_LOW:
        return []
    if not ctx.has_inference_data or ctx.request_count == 0:
        return []

    gpu_avg = ctx.avg_gpu_utilization
    # A saturated GPU is not starved of work: small batches are not the
    # binding constraint, so attributing the symptom to batching would be wrong.
    if gpu_avg is not None and gpu_avg >= 75.0:
        return []
    gpu_idle = gpu_avg is not None and gpu_avg < GPU_IDLE_PCT
    queue = ctx.queue_latency.avg
    queue_low = queue is not None and queue < 10.0
    batch_change = ctx.batch_size.change_pct
    gpu_change = ctx.avg_gpu_utilization is not None and any(
        (g.utilization.change_pct or 0) < GPU_UTIL_DROP_PCT for g in ctx.gpus
    )

    evidence = [
        f"Average batch size was {batch_avg:.1f} against a configured maximum of "
        f"{configured} ({efficiency * 100:.0f}% batch efficiency).",
        f"{ctx.request_count} requests were served in the window, so traffic was present.",
    ]
    if gpu_avg is not None:
        evidence.append(f"GPU utilisation averaged {_fmt(gpu_avg, '%')}.")
    if queue is not None:
        evidence.append(
            f"Queue latency averaged only {_fmt(queue, ' ms')}, so requests are being "
            "dispatched almost immediately rather than accumulating into batches."
        )
    if batch_change is not None and batch_change < -10:
        evidence.append(
            f"Average batch size fell {abs(batch_change):.1f}% within the window "
            f"({_fmt(ctx.batch_size.first_half_avg, '', 1)} → "
            f"{_fmt(ctx.batch_size.second_half_avg, '', 1)})."
        )

    # Estimated recoverable throughput, capped so the claim stays defensible.
    headroom = min(0.6, (1 - efficiency) * 0.55)
    window_ms = ctx.batch_window_ms
    recommendation_window = (
        f"Increase the dynamic batching window from {window_ms:.0f} ms to "
        f"{max(15.0, window_ms * 3):.0f} ms."
        if window_ms
        else "Increase the dynamic batching window (a 10-20 ms window is a common starting point)."
    )

    return [
        Finding(
            kind=DiagnosisKind.UNDER_BATCHING.value,
            title="GPU under-utilisation caused by under-batched inference requests",
            severity=(
                Severity.HIGH.value if (gpu_idle and efficiency < 0.2) else Severity.MEDIUM.value
            ),
            root_cause=(
                "Inference requests are being dispatched in batches far smaller than "
                "the configured maximum. Each kernel launch carries fixed overhead, so "
                "small batches leave the GPU idle between launches even under steady load."
            ),
            evidence=evidence,
            metrics={
                "avg_batch_size": round(batch_avg, 2),
                "configured_max_batch_size": configured,
                "batch_efficiency": round(efficiency, 3),
                "gpu_utilization_avg_pct": round(gpu_avg, 2) if gpu_avg is not None else None,
                "queue_latency_ms": round(queue, 2) if queue is not None else None,
                "request_count": ctx.request_count,
                "batch_size_change_pct": (
                    round(batch_change, 2) if batch_change is not None else None
                ),
            },
            impact=(
                f"Estimated recoverable throughput of approximately "
                f"{headroom * 100:.0f}% if batches were formed closer to the configured maximum."
            ),
            recommendations=[
                recommendation_window,
                f"Raise the maximum batch size above {configured} if VRAM headroom permits.",
                "Confirm clients issue requests concurrently rather than sequentially.",
                "Enable continuous batching if the serving backend supports it.",
            ],
            confidence=_confidence(
                [True, gpu_idle, queue_low, gpu_change, ctx.request_count > 100], base=0.5
            ),
            entity_type="deployment",
        )
    ]


# --------------------------------------------------------- 9. Over-batching --
def rule_over_batching(ctx: DiagnosticContext) -> list[Finding]:
    batch_avg = ctx.batch_size.avg
    configured = ctx.configured_max_batch
    if batch_avg is None or not configured:
        return []
    efficiency = batch_avg / configured
    depth = ctx.queue_depth.avg
    p99 = ctx.latency_p99.avg
    p50 = ctx.latency_p50.avg

    if efficiency < BATCH_EFFICIENCY_HIGH:
        return []
    if depth is None or depth < QUEUE_DEPTH_HIGH:
        return []

    tail_ratio = (p99 / p50) if (p99 and p50) else None
    evidence = [
        f"Average batch size is {batch_avg:.1f} against a maximum of {configured} "
        f"({efficiency * 100:.0f}% of capacity) -- batches are consistently full.",
        f"Queue depth averaged {depth:.1f} requests waiting behind full batches.",
    ]
    if tail_ratio:
        evidence.append(
            f"P99/P50 ratio is {tail_ratio:.1f}×, showing latency amplification at the tail."
        )

    return [
        Finding(
            kind=DiagnosisKind.OVER_BATCHING.value,
            title="Over-batching is inflating tail latency",
            severity=Severity.MEDIUM.value,
            root_cause=(
                "Batches are consistently forming at the configured ceiling while "
                "additional requests queue behind them. Throughput is maximised at the "
                "cost of per-request latency."
            ),
            evidence=evidence,
            metrics={
                "avg_batch_size": round(batch_avg, 2),
                "configured_max_batch_size": configured,
                "batch_efficiency": round(efficiency, 3),
                "queue_depth": round(depth, 2),
                "tail_ratio": round(tail_ratio, 2) if tail_ratio else None,
            },
            impact="Latency-sensitive clients see inflated response times despite high throughput.",
            recommendations=[
                "Reduce the batch formation window to admit requests sooner.",
                "Scale out replicas so batches do not need to absorb all offered load.",
                "Introduce priority routing so latency-sensitive traffic bypasses large batches.",
            ],
            confidence=_confidence(
                [True, bool(tail_ratio and tail_ratio > TAIL_RATIO_HIGH), depth > 15], base=0.45
            ),
            entity_type="deployment",
        )
    ]


# --------------------------------------------------- 10. Thermal throttling --
def rule_thermal_throttling(ctx: DiagnosticContext) -> list[Finding]:
    findings: list[Finding] = []
    for gpu in ctx.gpus:
        peak_temp = gpu.temperature.peak
        thermal_flags = [r for r in gpu.throttle_reasons if "thermal" in r]
        hot = peak_temp is not None and peak_temp >= THERMAL_LIMIT_C
        if not hot and not thermal_flags:
            continue

        clock_avg = gpu.sm_clock.avg
        clock_ratio = (clock_avg / gpu.max_clock_mhz) if (clock_avg and gpu.max_clock_mhz) else None
        evidence = []
        if peak_temp is not None:
            evidence.append(
                f"{gpu.label} peaked at {_fmt(peak_temp, '°C')} "
                f"(average {_fmt(gpu.temperature.avg, '°C')})."
            )
        if thermal_flags:
            evidence.append(f"NVML reported thermal throttle reasons: {', '.join(thermal_flags)}.")
        if clock_ratio is not None:
            evidence.append(
                f"SM clock averaged {_fmt(clock_avg, ' MHz', 0)} against a maximum of "
                f"{gpu.max_clock_mhz} MHz ({clock_ratio * 100:.0f}% of rated clock)."
            )

        findings.append(
            Finding(
                kind=DiagnosisKind.THERMAL_THROTTLING.value,
                title=f"Thermal throttling on {gpu.label}",
                severity=(
                    Severity.HIGH.value
                    if (clock_ratio and clock_ratio < 0.8)
                    else Severity.MEDIUM.value
                ),
                root_cause=(
                    "The device exceeded its thermal limit and the hardware reduced "
                    "clocks to protect itself. Sustained throughput falls even though "
                    "utilisation still reads high, because each clock cycle does less work."
                ),
                evidence=evidence,
                metrics={
                    "temperature_peak_c": round(peak_temp, 1) if peak_temp else None,
                    "temperature_avg_c": (
                        round(gpu.temperature.avg, 1) if gpu.temperature.avg else None
                    ),
                    "sm_clock_avg_mhz": round(clock_avg, 0) if clock_avg else None,
                    "max_clock_mhz": gpu.max_clock_mhz,
                    "clock_ratio": round(clock_ratio, 3) if clock_ratio else None,
                    "throttle_reasons": ", ".join(gpu.throttle_reasons) or None,
                },
                impact="Effective compute is reduced for the same power and cost.",
                recommendations=[
                    "Inspect chassis airflow, inlet temperature and fan curves.",
                    "Reduce sustained power limit to trade a little peak for stable clocks.",
                    "Redistribute the workload across additional devices.",
                    "Verify the device is seated correctly and heatsinks are unobstructed.",
                ],
                confidence=_confidence(
                    [hot, bool(thermal_flags), bool(clock_ratio and clock_ratio < 0.85)], base=0.55
                ),
                entity_type="gpu",
                entity_id=gpu.gpu_id,
                entity_label=gpu.label,
            )
        )
    return findings


# ---------------------------------------------------- 11. Power limitation --
def rule_power_limitation(ctx: DiagnosticContext) -> list[Finding]:
    findings: list[Finding] = []
    for gpu in ctx.gpus:
        power_avg = gpu.power.avg
        limit = gpu.power_limit_w
        power_flags = [r for r in gpu.throttle_reasons if "power" in r]
        if (power_avg is None or not limit) and not power_flags:
            continue
        ratio = (power_avg / limit) if (power_avg and limit) else None
        capped = ratio is not None and ratio >= POWER_LIMIT_RATIO
        if not capped and not power_flags:
            continue

        evidence = []
        if ratio is not None:
            evidence.append(
                f"{gpu.label} drew {_fmt(power_avg, ' W', 0)} against a "
                f"{_fmt(limit, ' W', 0)} enforced limit ({ratio * 100:.0f}%)."
            )
        if power_flags:
            evidence.append(f"NVML reported power throttle reasons: {', '.join(power_flags)}.")

        findings.append(
            Finding(
                kind=DiagnosisKind.POWER_LIMITATION.value,
                title=f"Power limit is constraining {gpu.label}",
                severity=Severity.MEDIUM.value,
                root_cause=(
                    "The device is running against its enforced power cap, so the "
                    "clock manager reduces frequency to stay within budget. Additional "
                    "load cannot translate into additional throughput."
                ),
                evidence=evidence,
                metrics={
                    "power_avg_w": round(power_avg, 1) if power_avg else None,
                    "power_limit_w": round(limit, 1) if limit else None,
                    "power_ratio": round(ratio, 3) if ratio else None,
                    "throttle_reasons": ", ".join(gpu.throttle_reasons) or None,
                },
                impact="Throughput is capped by the power budget rather than by compute capacity.",
                recommendations=[
                    "Raise the enforced power limit if the chassis and PSU allow it.",
                    "Verify the power limit was not lowered by a management policy.",
                    "Balance the workload across more devices to reduce per-device draw.",
                ],
                confidence=_confidence([capped, bool(power_flags)], base=0.5),
                entity_type="gpu",
                entity_id=gpu.gpu_id,
                entity_label=gpu.label,
            )
        )
    return findings


# ------------------------------------------------------ 12. High error rate --
def rule_high_error_rate(ctx: DiagnosticContext) -> list[Finding]:
    error_avg = ctx.error_rate.avg
    if error_avg is None or error_avg < ERROR_RATE_HIGH:
        return []

    change = ctx.error_rate.change_pct
    evidence = [f"Error rate averaged {error_avg * 100:.2f}% across the window."]
    if change is not None:
        evidence.append(f"Error rate changed {change:+.1f}% between the first and second half.")
    vram_peaks = [g.vram_pct.peak for g in ctx.gpus if g.vram_pct.peak is not None]
    if vram_peaks and max(vram_peaks) > VRAM_SATURATION_PCT:
        evidence.append(
            f"Peak VRAM utilisation reached {_fmt(max(vram_peaks), '%')}, a plausible "
            "contributing cause."
        )

    return [
        Finding(
            kind=DiagnosisKind.HIGH_ERROR_RATE.value,
            title="Elevated inference error rate",
            severity=Severity.CRITICAL.value if error_avg > 0.10 else Severity.HIGH.value,
            root_cause=(
                "A material share of inference requests are failing. Combined with the "
                "resource signals below, the most likely causes are capacity rejection "
                "or backend saturation rather than malformed input."
            ),
            evidence=evidence,
            metrics={
                "error_rate": round(error_avg, 4),
                "error_rate_change_pct": round(change, 2) if change is not None else None,
                "request_count": ctx.request_count,
            },
            impact="Clients are receiving failures; the effective success throughput is reduced.",
            recommendations=[
                "Inspect the request table filtered to errors and group by error type.",
                "Check whether VRAM saturation is causing allocation failures.",
                "Review upstream timeouts and gateway concurrency limits.",
                "Add retry with backoff on the client for transient capacity errors.",
            ],
            confidence=_confidence([True, error_avg > 0.05, bool(vram_peaks)], base=0.6),
            entity_type="deployment",
        )
    ]


# ------------------------------------------------------ 13. Model regression --
def rule_model_regression(ctx: DiagnosticContext) -> list[Finding]:
    latency_change = ctx.latency_p95.change_pct
    throughput_change = ctx.throughput.change_pct
    if latency_change is None or throughput_change is None:
        return []
    # A regression is a simultaneous latency rise and throughput fall.
    if latency_change < 20 or throughput_change > -15:
        return []
    gpu_change = ctx.avg_gpu_utilization
    thermal = any("thermal" in r for g in ctx.gpus for r in g.throttle_reasons)
    if thermal:
        return []  # Attributed to thermal throttling instead.

    return [
        Finding(
            kind=DiagnosisKind.MODEL_REGRESSION.value,
            title="Possible serving regression",
            severity=Severity.HIGH.value,
            root_cause=(
                "Latency increased and throughput decreased together, without a "
                "thermal or power explanation. This pattern is characteristic of a "
                "configuration or model-version regression."
            ),
            evidence=[
                f"P95 latency rose {latency_change:+.1f}% while throughput "
                f"fell {throughput_change:+.1f}%.",
                "No thermal throttle reasons were reported by any monitored device.",
                f"Average GPU utilisation was {_fmt(gpu_change, '%')}.",
            ],
            metrics={
                "p95_latency_change_pct": round(latency_change, 2),
                "throughput_change_pct": round(throughput_change, 2),
                "gpu_utilization_avg_pct": round(gpu_change, 2) if gpu_change is not None else None,
            },
            impact="Serving efficiency regressed on both latency and throughput axes.",
            recommendations=[
                "Diff the current deployment configuration against the last known-good revision.",
                "Confirm the model version and quantisation settings did not change.",
                "Roll back to the previous revision and re-measure to isolate the cause.",
                "Use the comparison tool to quantify the delta against the prior model.",
            ],
            confidence=_confidence([True, latency_change > 50, throughput_change < -30], base=0.4),
            entity_type="deployment",
        )
    ]


# ------------------------------------------- 14. Abnormal token throughput --
def rule_abnormal_token_throughput(ctx: DiagnosticContext) -> list[Finding]:
    change = ctx.tokens_per_second.change_pct
    if change is None or change > TOKEN_DROP_PCT:
        return []
    request_change = ctx.throughput.change_pct
    # Only interesting when token throughput falls faster than request volume.
    if request_change is not None and request_change <= change + 5:
        return []

    return [
        Finding(
            kind=DiagnosisKind.ABNORMAL_TOKEN_THROUGHPUT.value,
            title="Token throughput declined faster than request volume",
            severity=Severity.MEDIUM.value,
            root_cause=(
                "Tokens per second fell disproportionately relative to requests per "
                "second, meaning each request is producing fewer tokens or generating "
                "them more slowly."
            ),
            evidence=[
                f"Token throughput changed {change:+.1f}% "
                f"({_fmt(ctx.tokens_per_second.first_half_avg, ' tok/s')} → "
                f"{_fmt(ctx.tokens_per_second.second_half_avg, ' tok/s')}).",
                (
                    f"Request throughput changed {request_change:+.1f}% over the same window."
                    if request_change is not None
                    else "Request throughput was not available for comparison."
                ),
            ],
            metrics={
                "tokens_per_second_change_pct": round(change, 2),
                "throughput_change_pct": (
                    round(request_change, 2) if request_change is not None else None
                ),
                "tokens_per_second_avg": (
                    round(ctx.tokens_per_second.avg, 2) if ctx.tokens_per_second.avg else None
                ),
            },
            impact=(
                "Generation efficiency dropped; cost per token rises even if " "request rate holds."
            ),
            recommendations=[
                "Check whether decode is being preempted by VRAM pressure.",
                "Verify max_tokens and stop-sequence settings did not change.",
                "Compare input/output token ratios against the previous window.",
            ],
            confidence=_confidence([True, change < -40], base=0.45),
            entity_type="deployment",
        )
    ]


# ------------------------------------------------------------ 15. Cost spike --
def rule_cost_spike(ctx: DiagnosticContext) -> list[Finding]:
    if ctx.cost_change_pct is None or ctx.cost_change_pct < COST_SPIKE_PCT:
        return []
    throughput_change = ctx.throughput.change_pct
    efficiency_lost = throughput_change is not None and throughput_change < 5

    return [
        Finding(
            kind=DiagnosisKind.COST_SPIKE.value,
            title="Inference cost increased sharply",
            severity=Severity.HIGH.value if ctx.cost_change_pct > 60 else Severity.MEDIUM.value,
            root_cause=(
                "Estimated cost per unit of work rose"
                + (
                    " without a corresponding increase in delivered throughput."
                    if efficiency_lost
                    else " alongside increased throughput."
                )
            ),
            evidence=[
                f"Estimated cost changed {ctx.cost_change_pct:+.1f}% across the window.",
                (
                    f"Throughput changed {throughput_change:+.1f}% over the same period."
                    if throughput_change is not None
                    else "Throughput was not available for comparison."
                ),
            ],
            metrics={
                "cost_change_pct": round(ctx.cost_change_pct, 2),
                "cost_per_hour": round(ctx.cost_per_hour, 4) if ctx.cost_per_hour else None,
                "throughput_change_pct": (
                    round(throughput_change, 2) if throughput_change is not None else None
                ),
            },
            impact=(
                "Spend per delivered request is rising. All cost figures are "
                "estimates from configured pricing."
            ),
            recommendations=[
                "Review the active pricing profile for correctness.",
                "Investigate GPU under-utilisation -- idle paid capacity is the usual driver.",
                "Consolidate low-traffic deployments onto shared hardware.",
            ],
            confidence=_confidence([True, efficiency_lost], base=0.4),
            entity_type="deployment",
        )
    ]


ALL_RULES: list[tuple[str, Rule]] = [
    ("gpu_under_utilization", rule_gpu_under_utilization),
    ("vram_saturation", rule_vram_saturation),
    ("cpu_bottleneck", rule_cpu_bottleneck),
    ("memory_bottleneck", rule_memory_bottleneck),
    ("latency_spike", rule_latency_spike),
    ("throughput_degradation", rule_throughput_degradation),
    ("excessive_queueing", rule_excessive_queueing),
    ("under_batching", rule_under_batching),
    ("over_batching", rule_over_batching),
    ("thermal_throttling", rule_thermal_throttling),
    ("power_limitation", rule_power_limitation),
    ("high_error_rate", rule_high_error_rate),
    ("model_regression", rule_model_regression),
    ("abnormal_token_throughput", rule_abnormal_token_throughput),
    ("cost_spike", rule_cost_spike),
]
