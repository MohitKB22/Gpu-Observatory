# Testing

```bash
make test        # backend + frontend
make test-cov    # backend with coverage
make verify      # lint + types + tests + production build
```

## Philosophy

Tests assert behaviour that matters, not implementation detail. Several exist
specifically to protect the platform's core guarantees:

- Demo telemetry never lands in the production namespace.
- An unmeasured metric renders as `—`, never `0`.
- The diagnostics engine reaches the right conclusion for each scenario.
- The agent has no write capability and refuses injection.
- Error responses never leak internals or echo submitted values.

## Backend (180 tests)

| File | Focus |
|---|---|
| `test_health.py` | Liveness, readiness, metrics format, OpenAPI completeness, request IDs, security headers, logging configuration |
| `test_auth.py` | Password hashing, JWT issuance, refresh rotation and reuse detection, RBAC denials, API key lifecycle and scope enforcement, account enumeration resistance |
| `test_statistics.py` | Percentiles, robust vs classic z-score, EWMA, trend, edge cases |
| `test_collectors.py` | NVML graceful degradation, throttle decoding, DCGM parsing, unreachable exporters |
| `test_demo.py` | All seven scenarios, determinism, signal coherence, namespace isolation |
| `test_diagnostics.py` | All 15 rules registered; each scenario correctly identified; evidence and contract shape; supersession; coalescing |
| `test_anomaly.py` | Detection on spikes, silence on stable series, direction awareness |
| `test_agent.py` | Tool registry, read-only invariant, guard blocking and allowing, rules-only answers, honest no-data responses |
| `test_api_telemetry.py` | GPU and system endpoints, pagination bounds, time-range validation, honest empty states, namespace isolation |
| `test_api_inference.py` | Model registration and validation, percentile ordering, histograms, batching detection, comparison guards |
| `test_api_analytics.py` | Alert lifecycle and conflicts, anomaly scans, diagnosis contract, cost estimate labelling, agent endpoints |
| `test_api_demo.py` | Demo state, scenario switching, backfill, isolation of demo deletion |
| `test_security.py` | RBAC matrix, oversized bodies, SQL injection, path traversal, error hygiene, secret non-disclosure, production config validation |

Tests run against SQLite in-memory with a fresh database per test, so the whole
stack — models, migrations, services, HTTP layer — is exercised without
external services. CI additionally runs the migration cycle and an end-to-end
boot against real PostgreSQL and Redis.

### The scenario suite

`test_diagnostics.py` is the highest-value suite. For each of the seven demo
scenarios it seeds 40 minutes of telemetry, runs the engine, and asserts the
top finding matches the scenario:

| Scenario | Expected top finding |
|---|---|
| healthy | `healthy` |
| under_batching | `under_batching` |
| vram_pressure | `vram_saturation` |
| cpu_bottleneck | `cpu_bottleneck` |
| latency_spike | `latency_spike` |
| throughput_degradation | `throughput_degradation` |
| thermal_throttling | `thermal_throttling` |

This is an end-to-end check: generation → persistence → aggregation → context
assembly → rule evaluation → ranking. It has caught real bugs, including
mid-bucket aggregation that made throughput depend on wall-clock alignment.

## Frontend (31 tests)

| File | Focus |
|---|---|
| `format.test.ts` | Null renders as `—` and never as `0`; unit switching; relative time |
| `api.test.ts` | Error envelope parsing, retry classification, token attachment, single-flight refresh on 401, empty parameter omission |
| `states.test.tsx` | Loading announced to assistive technology, empty guidance, error hints and request IDs, retry, `QueryBoundary` state matrix, error boundary containment, KPI null handling, GPU-unavailable notice |

## Running subsets

```bash
cd apps/api
PYTHONPATH=. .venv/bin/pytest tests/test_diagnostics.py -v
PYTHONPATH=. .venv/bin/pytest -k "batching or vram"
PYTHONPATH=. .venv/bin/pytest --cov=app --cov-report=html   # htmlcov/index.html

cd apps/web
npx vitest run tests/api.test.ts
npx vitest            # watch mode
```

## CI

Nine jobs run on every push and pull request:

1. `backend-lint` — Ruff and Black
2. `backend-typecheck` — MyPy
3. `backend-tests` — full suite with coverage
4. `backend-integration` — migration up/down/up plus an end-to-end boot against real PostgreSQL and Redis
5. `frontend` — ESLint, `tsc --noEmit`, Vitest, production build
6. `manifests` — Helm lint and template, kubeconform, compose validation
7. `docker` — build all five images and assert none runs as root
8. `security` — Trivy, gitleaks, pip-audit, npm audit
9. `ci-passed` — gate requiring every job to succeed

## Writing tests

Prefer asserting the guarantee over the mechanism:

```python
async def test_overview_on_empty_production_returns_nulls_not_fabrications(client, admin_headers):
    body = (await client.get("/api/v1/overview", headers=admin_headers,
                             params={"source": "production"})).json()
    assert all(k["value"] is None for k in body["kpis"]), (
        "with no telemetry every KPI must be null rather than an invented number"
    )
```

Use the `seeded_demo` fixture for tests needing populated telemetry; it
backfills 40 minutes of the under-batching scenario.
