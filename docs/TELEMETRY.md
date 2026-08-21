# Telemetry

## Collectors

All collectors implement one interface and report their own availability, so
the API can state precisely why data is missing.

### NVML (`app/collectors/nvml.py`)

Primary source for NVIDIA hardware. Collects utilisation, memory, temperature,
power, SM and memory clocks, fan speed, PCIe throughput, ECC errors, decoded
throttle reasons, and per-process occupancy.

**Enumerates every device index.** It never assumes a single GPU at index 0.

**Degrades honestly.** If the library is missing or NVML fails to initialise,
`status()` returns `available=false` with a specific reason
(`nvml_library_not_installed`, `nvml_init_failed`, `no_nvidia_gpu_detected`),
and `sample()` returns an empty list. It never emits a fabricated reading.

Every individual NVML call is wrapped: a device that does not support fan-speed
reporting yields `null` for that field rather than failing the whole sweep.

### DCGM (`app/collectors/dcgm.py`)

Reads the Prometheus exposition published by `dcgm-exporter`, which is the
deployment shape used in Kubernetes with the GPU Operator. Parses the text
format directly, maps DCGM field names to the internal sample shape, and
derives memory utilisation when the exporter does not publish it. Unreachable
endpoints degrade to an empty sample with reason `dcgm_exporter_unreachable`.

### System (`app/collectors/system.py`)

psutil-based host metrics: CPU total and per-core, load average, RAM, swap,
disk, network throughput and process count. Network rates are derived between
consecutive calls rather than reported as cumulative counters.

### Demo (`app/demo/`)

Generates coherent synthetic telemetry for seven scenarios. Signals are
physically consistent: the under-batching scenario genuinely depresses batch
size *and* GPU utilisation together, rather than randomising independent
numbers. Latency is drawn from a log-normal shape so percentiles behave the way
real serving traffic does.

All demo output is written with `data_source='demo'`, and simulated devices are
named "… (simulated)" so a screenshot cannot be mistaken for real inventory.

## Ingestion

Two paths write telemetry:

**Embedded workers** — when the API runs on a GPU host, its background
supervisor collects locally on `TELEMETRY_INTERVAL_SECONDS`.

**Remote agents** — `services/telemetry-agent` runs on each GPU node (a
DaemonSet in Kubernetes), collects locally, and pushes to
`POST /api/v1/telemetry/ingest` using an API key with `telemetry:write`. On
sustained failure it backs off exponentially rather than hammering a downed API.

Inference telemetry arrives from the gateway via
`POST /api/v1/inference/requests`, which accepts up to 1000 records per call.

## Aggregation

```
raw samples ──► 60s rollups ──► dashboard queries
   (7 days)       (90 days)      (bucketed, ≤720 points)
```

`resolve_range()` picks the bucket width from the requested window, so a 7-day
range returns 15-minute buckets rather than a million raw points. Combining
buckets uses request-count weighting.

## Freshness

Every telemetry response includes a freshness block:

```json
{
  "last_sample_at": "2026-08-14T09:20:43Z",
  "age_seconds": 0.86,
  "is_stale": false,
  "expected_interval_seconds": 5
}
```

Data is stale after three missed intervals (minimum 30 seconds). The dashboard
header shows the age and marks it amber when stale, so a frozen chart is never
mistaken for a stable one.

## Prometheus

The API exposes `/metrics` in text exposition format.

**Platform self-observability**

| Metric | Type | Meaning |
|---|---|---|
| `nvo_http_requests_total` | counter | Requests by method, route template, status |
| `nvo_http_errors_total` | counter | Server errors |
| `nvo_http_request_duration_seconds` | histogram | API latency |
| `nvo_http_requests_in_progress` | gauge | Concurrent requests |
| `nvo_dependency_up` | gauge | Database and cache reachability |
| `nvo_telemetry_samples_total` | counter | Samples ingested, by kind and data source |
| `nvo_telemetry_failures_total` | counter | Collection or persistence failures |
| `nvo_telemetry_last_success_timestamp` | gauge | Staleness detection |
| `nvo_agent_requests_total` | counter | Agent invocations by engine and outcome |
| `nvo_agent_duration_seconds` | histogram | Agent latency |
| `nvo_agent_tool_calls_total` | counter | Tool usage |
| `nvo_websocket_connections` | gauge | Open sockets |
| `nvo_rate_limit_rejections_total` | counter | Throttled requests |
| `nvo_retention_rows_deleted_total` | counter | Rows swept |

**Observed workload telemetry**

| Metric | Labels |
|---|---|
| `nvo_gpu_utilization_percent` | `gpu_uuid`, `gpu_index`, `gpu_name`, `data_source` |
| `nvo_gpu_memory_used_megabytes` | `gpu_uuid`, `gpu_index`, `data_source` |
| `nvo_gpu_temperature_celsius` | `gpu_uuid`, `gpu_index`, `data_source` |
| `nvo_gpu_power_watts` | `gpu_uuid`, `gpu_index`, `data_source` |
| `nvo_inference_requests_total` | `deployment`, `status`, `data_source` |
| `nvo_inference_latency_seconds` | `deployment`, `data_source` |
| `nvo_inference_tokens_total` | `deployment`, `direction`, `data_source` |
| `nvo_alerts_active` | `severity` |

Note the `data_source` label: demo and production series are distinguishable in
Prometheus and Grafana too, not only in the application.

Route templates (`/api/v1/gpus/{gpu_id}`) are used as labels rather than raw
paths, so cardinality stays bounded.

## Anomaly detection

Robust statistics by default. A median/MAD z-score is not masked by the very
outlier it is trying to find, unlike a mean/stdev z-score.

| Method | Use |
|---|---|
| Robust z-score (median/MAD) | Primary; falls back to a scaled mean absolute deviation when a signal is pinned at a constant and MAD collapses to zero |
| EWMA | Divergence from a smoothed baseline |
| Percentile ceiling | Breach of a historical P99 |

Detection is direction-aware: a drop in latency is good news, not an anomaly.
A minimum of `ANOMALY_MIN_SAMPLES` (default 20) is required before any
detection runs, and repeat detections for the same signal are suppressed for
five minutes.
