# Database

PostgreSQL is the production target (via `asyncpg`). SQLite (`aiosqlite`) is
supported for local development and the test-suite, so the whole stack can be
exercised without external services.

## Portability decisions

**String UUID primary keys.** Portable across both backends without extension
dependencies, and safe to expose in URLs.

**`UTCDateTime` type decorator.** Every datetime column normalises to
timezone-aware UTC on both bind and result. SQLite drops `tzinfo` on
round-trip, which otherwise produces naive/aware comparison crashes at runtime.
Normalising in one place removes the entire class of bug.

**Python-side bucketing.** Time buckets are computed in application code rather
than with dialect-specific SQL (`date_trunc` vs `strftime`), keeping one code
path for both backends.

## Schema

19 tables in five groups.

### Authentication

| Table | Purpose | Notable columns |
|---|---|---|
| `users` | Operator accounts | `email` (unique), `hashed_password` (Argon2id), `role`, `failed_login_count`, `locked_until` |
| `refresh_tokens` | Revocable sessions | `token_hash` (unique), `expires_at`, `revoked_at` |
| `api_keys` | Machine credentials | `key_hash` (unique, keyed HMAC), `prefix`, `scopes`, `expires_at` |
| `audit_logs` | Append-only security trail | `action`, `outcome`, `actor_type`, `request_id`, `source_ip` |

### Telemetry

| Table | Purpose | Notable columns |
|---|---|---|
| `gpus` | Device inventory | `uuid`+`data_source` (unique), `index`, `total_memory_mb`, `power_limit_w` |
| `gpu_metrics` | Per-sample readings | `utilization_pct`, `memory_utilization_pct`, `temperature_c`, `power_w`, `sm_clock_mhz`, `throttle_reasons` |
| `gpu_processes` | Process occupancy snapshot | `pid`, `used_memory_mb`, `workload_label` |
| `system_metrics` | Host metrics | `cpu_utilization_pct`, `per_core_utilization` (JSON), `ram_utilization_pct`, network rates |

### Inference

| Table | Purpose | Notable columns |
|---|---|---|
| `ml_models` | Model registry | `name`+`version`+`data_source` (unique), `quantization`, `max_batch_size` |
| `deployments` | Model on hardware | `model_id`, `gpu_id`, `max_batch_size`, `batch_window_ms`, `tensor_parallel_size` |
| `inference_requests` | Raw observed requests | `total_latency_ms` plus stage timings, tokens, `batch_size`, `is_error` |
| `inference_metrics` | 60s rollups | percentiles, `requests_per_second`, `tokens_per_second`, `avg_batch_size` |
| `batch_metrics` | Batching rollups | `avg_batch_size`, `configured_max_batch_size`, `batch_efficiency`, `queue_depth` |

### Analytics

| Table | Purpose |
|---|---|
| `anomalies` | Detected deviations with method, score, observed and expected values |
| `alert_rules` | Configurable thresholds with `for_seconds` and `cooldown_seconds` |
| `alerts` | Fired instances with the active → acknowledged → resolved lifecycle |
| `diagnoses` | Stored findings; `evidence`, `metrics` and `recommendations` as JSON text |
| `pricing_profiles` | Configurable rates; `is_estimate` always true |
| `workloads` | Synthetic load runs and their outcomes |

## The `data_source` discriminator

Every telemetry, inference and analytics table carries `data_source`
(`production` | `demo`), indexed and included in composite indexes.

- Every read path filters on it.
- Uniqueness constraints include it, so a demo and a production GPU may share a
  UUID without collision.
- `reset_demo_data()` deletes only `data_source='demo'` rows.

This is the mechanism that makes "synthetic data is never presented as
production data" a structural property rather than a convention.

## Indexes

Composite indexes match the actual query shapes:

| Index | Serves |
|---|---|
| `ix_gpu_metrics_gpu_time` (`gpu_id`, `recorded_at`) | Per-device series |
| `ix_gpu_metrics_source_time` (`data_source`, `recorded_at`) | Namespace-scoped window scans |
| `ix_inference_requests_dep_time` (`deployment_id`, `started_at`) | Request tables |
| `ix_inference_metrics_source_bucket` (`data_source`, `bucket_start`) | Dashboard series |
| `uq_inference_metrics_bucket` (`deployment_id`, `bucket_start`, `bucket_seconds`, `data_source`) | Idempotent rollup upserts |
| `ix_alerts_state_time` (`state`, `triggered_at`) | Alert list |
| `ix_anomalies_source_time` (`data_source`, `detected_at`) | Anomaly list |

## Aggregation

Raw telemetry is never scanned for a dashboard request.

1. The gateway writes individual rows to `inference_requests`.
2. Every 60 seconds a worker rolls the closed bucket into `inference_metrics`
   and `batch_metrics`.
3. Dashboards read the rollups. `resolve_range()` chooses a bucket width so any
   series stays under ~720 points.

Rollups are computed only after every request in a bucket has been written.
Aggregating mid-bucket would understate throughput in a way that varies with
wall-clock alignment.

Weighted averaging is used when combining buckets: a bucket with three requests
must not count as much as one with three thousand.

## Retention

| Data | Variable | Default |
|---|---|---|
| Raw telemetry and requests | `RETENTION_RAW_DAYS` | 7 days |
| Rollups and anomalies | `RETENTION_AGGREGATED_DAYS` | 90 days |
| Historical summaries | `RETENTION_SUMMARY_DAYS` | 365 days |

A sweeper runs every `RETENTION_SWEEP_INTERVAL_SECONDS` (default 1 hour) and
reports rows deleted per table via `nvo_retention_rows_deleted_total`.

## Migrations

```bash
make migrate                      # alembic upgrade head
make migrate-down                 # roll back one
make migration m="add x"          # autogenerate
```

The initial revision `0001_initial` creates all 19 tables with 117 indexes. It
is verified in CI against a real PostgreSQL with a full
upgrade → downgrade → upgrade cycle.

In Kubernetes, migrations run as an `initContainer` on the API deployment, so
the schema is always current before any pod serves traffic.

## Time-series scaling

The schema is TimescaleDB-compatible. To adopt it:

```sql
SELECT create_hypertable('gpu_metrics', 'recorded_at', migrate_data => true);
SELECT create_hypertable('inference_requests', 'started_at', migrate_data => true);
SELECT add_retention_policy('gpu_metrics', INTERVAL '7 days');
```

The application requires no changes: it already writes append-only rows keyed
by time and reads through bucketed aggregates.
