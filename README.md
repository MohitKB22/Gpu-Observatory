# NVIDIA AI Performance Observatory

Observability and performance-optimisation platform for NVIDIA AI inference
workloads. It collects GPU, host and inference telemetry, persists and
aggregates it, detects anomalies, and produces root-cause diagnoses backed by
the measurements it actually observed.

```
GPU / host telemetry ──┐
inference requests ────┼──► aggregation ──► diagnostics ──► "GPU utilisation is
batching signals ──────┘                    (15 rules)      32.8% because batches
                                                            average 2.3 of 32"
```

---

## What makes this different

**No fabricated data.** Every displayed number traces to a stored sample. A
metric that was not measured returns `null` and renders as `—`, never `0`. With
no NVIDIA GPU present the platform states that plainly instead of inventing
hardware statistics.

**Demo data is quarantined.** Every telemetry row carries a `data_source` of
`production` or `demo`; every read filters on it. Synthetic data can never be
presented as production telemetry.

**Diagnosis without an LLM.** Fifteen deterministic rules run against stored
measurements and produce the full structured diagnosis — title, severity, root
cause, evidence, metrics, impact, recommendations and confidence. A language
model is optional and only ever narrates findings it did not compute.

**The agent cannot do damage.** All 11 agent tools are read-only. There is no
tool to run a command, write data, or read secrets — enforced by absence of the
capability, not by prompt instructions.

---

## Screens

| Screen | Purpose |
|---|---|
| **Overview** | Eight KPIs, GPU/latency/throughput charts, the latest AI diagnosis, active alerts |
| **GPU Monitor** | Per-device inventory, live readings, throttle reasons, process occupancy, host system |
| **Inference** | Percentiles, latency distribution, stage breakdown, batching analytics, request table |
| **Models** | Model registry with registration, per-model measured performance, deployments |
| **Comparisons** | Two-to-six-model comparison with a computed recommendation |
| **AI Diagnostics** | Run diagnoses, ask the Performance Copilot, review anomalies and history |
| **Cost** | Estimated GPU-hours, cost per request and per million tokens, pricing profiles |
| **Alerts** | Active → acknowledged → resolved lifecycle, rule configuration |
| **Workloads** | Switch demo scenarios, generate synthetic load |
| **Settings** | Session, connection status, dashboard defaults, agent capabilities |

---

## Quick start

Requires Docker and Docker Compose. No NVIDIA hardware is needed.

```bash
git clone <repository-url>
cd nvidia-ai-performance-observatory

cp .env.example .env
# Set at minimum:
#   SECRET_KEY               (openssl rand -base64 48)
#   BOOTSTRAP_ADMIN_PASSWORD (12+ characters)

docker compose up -d --build
./scripts/healthcheck.sh
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:3000 |
| API documentation | http://localhost:8000/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3001 (admin/admin) |

Sign in with `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD`. The stack
starts in Demo Mode and backfills 90 minutes of labelled synthetic telemetry, so
every screen has data immediately.

### Local development without Docker

```bash
make setup          # backend virtualenv + frontend dependencies
make env            # create .env
make migrate        # apply migrations
make dev-api        # terminal 1 — http://localhost:8000
make dev-web        # terminal 2 — http://localhost:3000
```

SQLite works for local development:
`DATABASE_URL=sqlite+aiosqlite:///./nvo.db`

---

## Demo Mode

Demo Mode generates coherent synthetic telemetry for seven scenarios. Each
produces physically consistent signals, so the diagnostics engine has something
real to reason about.

| Scenario | Signals | Expected diagnosis |
|---|---|---|
| Healthy GPU | High utilisation, batches near max, stable latency | `healthy` |
| Under-batching | Batch 2.3/32, GPU ~33%, low queue time | `under_batching` |
| VRAM pressure | VRAM >96%, elevated errors, heavy tail | `vram_saturation` |
| CPU bottleneck | CPU ~96%, GPU ~37%, high queue time | `cpu_bottleneck` |
| Latency spike | P95 rising sharply, P99/P50 ≈ 8× | `latency_spike` |
| Throughput degradation | Throughput declining, demand steady | `throughput_degradation` |
| Thermal throttling | >85 °C, SM clock at 62% of rated | `thermal_throttling` |

Switch scenarios from **Workloads**, or:

```bash
curl -X POST "http://localhost:8000/api/v1/demo/scenario" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"scenario":"under_batching"}'
```

Demo data lives in its own namespace and is deleted independently:

```bash
curl -X DELETE "http://localhost:8000/api/v1/demo/data" -H "Authorization: Bearer $TOKEN"
```

---

## Running with real NVIDIA GPUs

Requires the NVIDIA driver, Container Toolkit, and `DEMO_MODE=false`.

```bash
# 1. Install the NVIDIA Container Toolkit, then verify:
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi

# 2. Mint an agent credential:
python scripts/create_api_key.py --name telemetry-agent \
  --scopes telemetry:read telemetry:write

# 3. Start with the GPU profile:
DEMO_MODE=false AGENT_API_KEY=nvo_live_... docker compose --profile gpu up -d
```

On Kubernetes the agent runs as a DaemonSet restricted to nodes labelled
`nvidia.com/gpu.present=true`. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

If no GPU is detected the platform reports `nvml_available: false` with a
specific reason and shows an explicit "NVIDIA GPU unavailable" notice.

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for seven Mermaid diagrams
covering system architecture, telemetry flow, inference flow, diagnosis flow,
the ER model, and both deployment topologies.

**Tech stack**

| Layer | Choice |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript (strict), Tailwind, TanStack Query, Zustand, Recharts |
| Backend | Python 3.11, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Data | PostgreSQL (asyncpg), Redis, SQLite for development and tests |
| Telemetry | NVML (`nvidia-ml-py`), DCGM exporter adapter, psutil, `prometheus-client` |
| Inference | vLLM, NVIDIA Triton, OpenAI-compatible and local adapters |
| AI | Provider abstraction (OpenAI / Anthropic / Ollama / none) over a deterministic rules engine |
| Infrastructure | Docker, Compose, Kubernetes, Helm, Prometheus, Grafana, GitHub Actions |

---

## API

Interactive documentation at `/docs`; the OpenAPI schema at `/openapi.json`.

```
GET    /health                              liveness
GET    /ready                               readiness (checks dependencies)
GET    /metrics                             Prometheus exposition

POST   /api/v1/auth/login                   obtain a token pair
GET    /api/v1/gpus                         list GPUs
GET    /api/v1/gpus/{id}                    device detail + processes
GET    /api/v1/gpus/{id}/metrics            raw samples (paginated)
GET    /api/v1/system/metrics               host metrics
GET    /api/v1/overview                     dashboard KPIs
GET    /api/v1/models                       model registry
POST   /api/v1/models                       register a model
GET    /api/v1/inference/metrics            percentiles and throughput
GET    /api/v1/inference/latency            latency histogram
GET    /api/v1/batches                      batching analytics
GET    /api/v1/comparisons/models           side-by-side comparison
GET    /api/v1/anomalies                    detected anomalies
GET    /api/v1/alerts                       alerts
POST   /api/v1/alerts/{id}/acknowledge      acknowledge
GET    /api/v1/cost                         cost estimate
POST   /api/v1/diagnostics                  run a diagnosis
GET    /api/v1/diagnostics/history          past diagnoses
POST   /api/v1/agent/chat                   ask the Performance Copilot
WS     /ws/telemetry                        live telemetry stream
```

Full reference: [docs/API.md](docs/API.md).

---

## Testing

```bash
make test        # backend (180 tests) + frontend (31 tests)
make verify      # lint + types + tests + production build
```

| Suite | Coverage |
|---|---|
| Backend unit | Statistics, collectors, demo generator, guard, RBAC |
| Backend API | Every endpoint, auth, RBAC, pagination, validation, error envelopes |
| Diagnostics | All seven scenarios end-to-end from seeded telemetry |
| Security | Injection resistance, error hygiene, secret non-disclosure, config validation |
| Frontend | Formatters, API client (refresh/retry), state components, error boundaries |

See [docs/TESTING.md](docs/TESTING.md).

---

## Deployment

```bash
# Kubernetes
kubectl apply -k infra/kubernetes/base

# Helm
helm install nvo infra/helm/nvidia-ai-performance-observatory \
  --namespace nvo --create-namespace \
  --set ingress.host=observatory.example.com \
  --set telemetryAgent.enabled=true
```

Secrets are never templated into manifests — create them out-of-band. See
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and [docs/SECURITY.md](docs/SECURITY.md).

---

## Documentation

| Document | Contents |
|---|---|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design principles, 7 diagrams, module layout |
| [API.md](docs/API.md) | Endpoint reference, auth, pagination, errors |
| [DATABASE.md](docs/DATABASE.md) | Schema, indexes, retention, migrations |
| [AI_AGENT.md](docs/AI_AGENT.md) | Rules engine, tools, safety model, prompt guard |
| [TELEMETRY.md](docs/TELEMETRY.md) | Collectors, ingestion, aggregation, Prometheus |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md) | Compose, Kubernetes, Helm, GPU enablement |
| [SECURITY.md](docs/SECURITY.md) | Auth, RBAC, rate limiting, agent boundaries |
| [TESTING.md](docs/TESTING.md) | Strategy, suites, how to run |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common failures and fixes |
| [CONTRIBUTING.md](docs/CONTRIBUTING.md) | Workflow, standards, review criteria |

---

## Known limitations

- **Per-process GPU accounting** requires NVML process APIs, which are
  unavailable in some virtualised and MIG configurations. The UI states this
  rather than showing an empty table without explanation.
- **Cost is an estimate**, computed as observed GPU-hours × a configurable
  rate. It is not billing data and is labelled as an estimate everywhere.
- **The bundled PostgreSQL and Redis manifests** are for evaluation. Use a
  managed service or an operator in production.
- **The local inference adapter performs no model computation.** It exists so
  the gateway and its instrumentation can be exercised without a serving
  backend, and it says so in its own response payload.
- **Model comparison needs traffic on both models.** With data on only one, the
  tool declines to recommend rather than guessing.

## License

Apache 2.0 — see [LICENSE](LICENSE).
