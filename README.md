# AI Inference Observatory

Model serving and performance observability for LLM inference endpoints. Register OpenAI-compatible,
vLLM and Hugging Face endpoints, run prompts against them, and watch latency percentiles, throughput,
errors, connection health and serving infrastructure, all from requests the platform actually recorded.

It runs fully offline in **demo mode** (no GPU, no paid API) and switches to **real mode** by registering
real endpoints. Demo data is labelled everywhere it appears and can be excluded with one switch.

**Live demo:** https://ai-inference-observatory-8dp7.onrender.com. It is a locked public demo that runs on demo
data only, so every figure it shows is labelled sample data, not production metrics. It runs on a free instance
that sleeps when idle, so the first load can take about a minute.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/MohitKB22/Gpu-Observatory)

![Overview](docs/screenshots/overview.png)

## Contents

- [Modules](#modules)
- [Data integrity rules](#data-integrity-rules)
- [Quick start](#quick-start-docker)
- [Public demo deployment](#public-demo-deployment)
- [Connecting a real endpoint](#connecting-a-real-endpoint)
- [Architecture](#architecture)
- [How metrics are calculated](#how-metrics-are-calculated)
- [API](#api)
- [Configuration](#configuration)
- [Local development](#local-development)
- [Testing](#testing)
- [Security](#security)
- [Known limitations](#known-limitations)
- [Deployment guide](DEPLOYMENT.md)

## Modules

| Module | What it does |
|---|---|
| **Overview** | Requests, P95 latency, generation speed and error rate for 1h/6h/24h/7d with change vs the previous period; traffic + P95 chart; live system health (database, CPU, memory, GPU); per-model status and traffic. |
| **Model Registry** | Register, edit, enable/disable and delete models; encrypted API keys; on-demand connection checks plus a background check every minute; per-model check history. |
| **Inference Playground** | Pick an enabled model, set system prompt, temperature and max tokens, run inference, and see the response with measured latency, token counts (exact or estimated) and generation speed. Every run is recorded. |
| **Performance Analytics** | P50/P95/P99 latency over time, request rate, token throughput, error rate, per-model comparison table and P95-by-model chart, filterable by model and window. |
| **Infrastructure** | Host CPU, memory, disk and load; the API worker process; CPU/memory/GPU history; GPU utilisation, memory, temperature and power via NVML or nvidia-smi; live queue and KV-cache usage scraped from vLLM servers; database and endpoint health. |
| **Request Logs** | Searchable history (prompt, response, error text, request ID) with model, status, source, data-source and time filters, pagination, and a detail panel with the full request, response, parameters, metrics and error. Filters live in the URL, so views can be shared. |

| Model Registry | Playground |
|---|---|
| ![Model registry](docs/screenshots/model-registry.png) | ![Playground](docs/screenshots/playground.png) |
| **Performance Analytics** | **Infrastructure** |
| ![Analytics](docs/screenshots/performance-analytics.png) | ![Infrastructure](docs/screenshots/infrastructure.png) |
| **Request Logs** | **Recorded failure** |
| ![Logs](docs/screenshots/request-logs.png) | ![Failure detail](docs/screenshots/request-detail-error.png) |

## Data integrity rules

These are enforced in code and covered by tests:

- **Demo data is always labelled.** Demo models use the `demo` provider; every request they serve and
  every seeded sample row is stored with `is_demo = true`. Every analytics response reports how many
  demo and real requests it includes, and the UI shows a banner whenever demo data contributes.
  The global *Data source* selector switches between *All*, *Real only* and *Demo only*.
  Outside demo mode the default is *Real only*.
- **No invented GPU numbers.** GPU metrics come from NVML or `nvidia-smi`. When neither is available,
  the API returns `available: false` with the reason and the UI shows an "unavailable" state.
- **Exact vs estimated tokens.** Counts are `exact` only when the provider reported all of them
  (OpenAI-compatible `usage`). Otherwise they are estimated at ~4 characters/token and stored as
  `estimated`; the UI prefixes them with `~` and labels them.
- **Real timings.** Latency is measured in the backend around the actual provider call
  (`time.perf_counter`), including failures.
- **No pretend operations.** *Enabled* only controls whether the Observatory sends traffic to a model.
  The app never claims to deploy, start or stop a model.
- **API keys stay on the backend.** They are encrypted at rest and never returned by the API.

## Quick start (Docker)

Requirements: Docker with Compose v2.24+.

```bash
docker compose up --build
```

| URL | |
|---|---|
| http://localhost:8080 | Dashboard |
| http://localhost:8000/api/docs | Interactive API docs (OpenAPI) |
| http://localhost:8000/metrics | Prometheus metrics |

The first start runs database migrations, registers three demo models (`demo-swift-1b`,
`demo-orbit-8b`, `demo-atlas-70b`) and seeds seven days of labelled sample traffic. No `.env` file is
needed. To change settings, `cp .env.example .env` and edit it.

Ports bind to `127.0.0.1` by default because the dashboard has no built-in login
(see [Security](#security)).

## Public demo deployment

The live instance is at https://ai-inference-observatory-8dp7.onrender.com (Render free web service in
Singapore, Neon free PostgreSQL).

`render.yaml` deploys a locked public demo on free tiers: one Render web service (the root `Dockerfile`
builds the dashboard and serves it from the API process) plus a free Neon PostgreSQL database. Click
**Deploy to Render** above and paste the Neon connection string when asked; step-by-step instructions are in
[DEPLOYMENT.md](DEPLOYMENT.md#public-demo-on-render--neon-free).

With `PUBLIC_DEMO=true` the Model Registry is read-only (registering, editing and deleting return 403), so
the server never calls a URL a visitor supplied. The Playground runs demo models only, with tighter input
limits and a per-visitor and global rate limit, and only the newest visitor runs are kept in the database.

## Connecting a real endpoint

Open **Model Registry → Register model**:

| Provider | Endpoint URL | Model ID | Token counts |
|---|---|---|---|
| OpenAI-compatible (OpenAI, Together, Groq, Mistral, LM Studio, …) | API base incl. `/v1`, e.g. `https://api.openai.com/v1` | e.g. `gpt-4o-mini` | exact (from `usage`) |
| Ollama on the Docker host | `http://host.docker.internal:11434/v1` | e.g. `llama3.1` | exact |
| vLLM | `http://gpu-server:8000/v1` | the served model name | exact |
| Hugging Face Inference Endpoint / TGI | the endpoint URL | the repo ID (for reference) | estimated |
| Hugging Face serverless | `https://api-inference.huggingface.co/models/<repo>` | the repo ID | estimated |

Click **Check connection** (a cheap `GET /models` or `/health`, no tokens spent), then select the
model in the **Playground**. Set **Data source → Real only** to see only real traffic. Turn demo mode off
for production with `DEMO_MODE=false`; see [DEPLOYMENT.md](DEPLOYMENT.md#going-to-production).

vLLM models also get live **running/waiting requests and KV-cache usage** on the Infrastructure page,
scraped from the server's `/metrics`. This is the way to watch a remote GPU server.

## Architecture

```
 Browser ──► nginx (frontend container) ──/api──► FastAPI backend ──► PostgreSQL 16
             static React build                    │  ├─ providers: demo · OpenAI-compatible · vLLM · Hugging Face ──► model endpoints
                                                   │  ├─ health-check scheduler (every 60 s) ──────────────────────► model endpoints
                                                   │  ├─ system sampler: psutil + NVML / nvidia-smi
                                                   │  └─ vLLM /metrics scraper ───────────────────────────────────► vLLM servers
                                                   └─ /metrics ◄── Prometheus (optional)
```

```
.
├── backend/
│   ├── app/
│   │   ├── api/            routes, dependencies, error handlers, request-logging middleware
│   │   ├── db/             SQLAlchemy base + async engine/session factory
│   │   ├── models/         ORM tables and enums
│   │   ├── schemas/        Pydantic request/response models (validation lives here)
│   │   ├── services/       business logic: inference, registry, health checks, analytics, logs, demo seed
│   │   ├── providers/      one module per inference backend behind a shared interface
│   │   ├── monitoring/     psutil, GPU, vLLM scraping, background sampler, Prometheus metrics
│   │   ├── config.py       environment-driven settings
│   │   ├── security.py     API-key encryption
│   │   ├── cli.py          maintenance commands (reseed / purge demo data)
│   │   └── main.py         app factory and lifespan
│   ├── alembic/            migrations
│   ├── tests/              pytest suite (runs against PostgreSQL)
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── api/            typed API client and endpoint functions
│   │   ├── components/     layout, UI primitives, charts
│   │   ├── features/       one folder per module (overview, models, playground, analytics, infrastructure, logs)
│   │   ├── context/        data-source selection, toasts
│   │   ├── hooks/ lib/     data fetching, formatting, helpers
│   │   └── test/           test setup and helpers
│   ├── nginx/              production server config (SPA + /api proxy + security headers)
│   └── Dockerfile
├── docs/screenshots/
├── docker-compose.yml       db + backend + frontend
├── docker-compose.gpu.yml   optional: expose NVIDIA GPUs to the backend
├── docker-compose.dev.yml   optional: publish the database for local development
├── Dockerfile               single-container image (dashboard served by the API), used by render.yaml
├── render.yaml              Render Blueprint for the free public demo
├── .env.example
├── DEPLOYMENT.md
└── .github/workflows/ci.yml
```

### Data model

| Table | Purpose |
|---|---|
| `registered_models` | Endpoint configuration, encrypted API key, enabled flag, latest connection-check status. |
| `inference_requests` | One row per attempt: prompt, response, parameters, status, error kind/message, `is_demo`, `source`, model name snapshot. |
| `request_metrics` | Narrow 1:1 table of numeric measurements (latency, tokens, token-count source, tokens/s), kept separate so analytics scan small rows instead of large text. |
| `health_checks` | History of connection checks (pruned after `HEALTH_CHECK_RETENTION_DAYS`). |

Deleting a model keeps its request history (`model_id` becomes NULL; the name is preserved) and
removes its check history. Schema changes go through Alembic; a test fails if the models drift from
the migrations.

### Design references

The UI follows the data-dense dashboard guidance from
[UI/UX Pro Max](https://github.com/Chonwai/dsh-uupm) (used as a methodology reference, not a template).
That means compact KPI cards and a dense grid; status always shown as colour plus text; visible focus
rings, labelled inputs, inline errors announced with `role="alert"` and skeleton loading states; series
told apart by line style (solid/dashed/dotted) as well as colour; comparison bars sorted by value;
`prefers-reduced-motion` respected; layouts checked at 390 px and 1440 px.

Palette: background `#0B1220`, sidebar `#101827`, cards `#151F30`, elevated `#1B293D`, borders
`#263449`, text `#F8FAFC` / `#94A3B8`, blue `#3B82F6`, violet `#8B5CF6`, green `#22C55E`,
amber `#F59E0B`, red `#EF4444`. Typography is Inter, with JetBrains Mono for figures, both self-hosted.

## How metrics are calculated

All aggregation runs in PostgreSQL (`percentile_cont`, `FILTER`) over the selected window and data source.

| Metric | Definition |
|---|---|
| P50 / P95 / P99 latency | Continuous percentiles of end-to-end latency over **successful** requests (so 60 s timeouts don't distort serving latency; they appear in the error rate). |
| Error rate | Failed requests ÷ all requests. |
| Request rate | Requests ÷ window length (shown per second, minute or hour, whichever is readable). |
| Generation speed (tok/s) | Mean over successful requests of `completion_tokens ÷ end-to-end latency`. Requests are not streamed, so time-to-first-token is not separated out. |
| Token throughput | All prompt + completion tokens ÷ window length. |
| Exact token share | Successful requests whose counts were reported by the provider. |
| Δ vs previous | The same metric over the immediately preceding window of equal length. |

## API

Base path `/api`. Full interactive documentation at `/api/docs`.

| Method | Path | |
|---|---|---|
| GET | `/health` | Liveness + database check (503 when the database is unreachable) |
| GET | `/system/info` | Version, environment, demo mode, default data source |
| GET | `/overview?window=&data_source=` | Overview page payload |
| GET | `/analytics?window=&data_source=&model_id=` | Summary, time series and per-model comparison |
| GET / POST | `/models` | List / register models |
| GET / PATCH / DELETE | `/models/{id}` | Read / partially update / delete |
| POST | `/models/{id}/check` | Run a connection check now |
| GET | `/models/{id}/health-checks?limit=` | Check history |
| POST | `/inference` | Run and record a completion (see below) |
| GET | `/infrastructure` | Host, worker, GPU, database, endpoint and vLLM server snapshot |
| GET | `/infrastructure/history` | In-memory utilisation samples |
| GET | `/logs?search=&model_id=&status=&source=&data_source=&window=&page=&page_size=` | Request history |
| GET | `/logs/{id}` | Full request record |
| GET | `/metrics` (no `/api` prefix) | Prometheus exposition |

`POST /api/inference` returns **200 with `status: "error"`** when the upstream endpoint fails
(timeout, HTTP error, bad response), because the attempt was executed and recorded. Requests that never
reach a provider (unknown or disabled model, invalid input) return 4xx. Errors use one shape:
`{"error": {"code": "...", "message": "...", "details": [{"field": "...", "message": "..."}]}}`.

```bash
curl -s localhost:8000/api/inference -H 'content-type: application/json' \
  -d '{"model_id": "<uuid>", "prompt": "Hello", "temperature": 0.2, "max_tokens": 64}'
```

## Configuration

All settings are environment variables (see [.env.example](.env.example) for the annotated list).

| Variable | Default | |
|---|---|---|
| `APP_ENV` | `development` | `production` refuses to start without a real `SECRET_KEY` |
| `SECRET_KEY` | insecure placeholder | Encrypts stored API keys; 32+ random chars; keep stable |
| `DATABASE_URL` | compose `db` service | `postgres://`, `postgresql://` and `postgresql+psycopg://` accepted |
| `DEMO_MODE` / `DEMO_SEED_HISTORY` / `DEMO_SIMULATE_LATENCY` | `true` | Demo models, sample history, simulated latency |
| `HEALTH_CHECK_INTERVAL_SECONDS` | `60` | Background checks of enabled models; `0` disables |
| `HEALTH_CHECK_RETENTION_DAYS` | `7` | Check history retention |
| `SYSTEM_SAMPLE_INTERVAL_SECONDS` / `SYSTEM_HISTORY_SIZE` | `5` / `720` | Utilisation sampling (≈1 hour of history) |
| `LOG_LEVEL` / `LOG_FORMAT` | `INFO` / `json` | Structured JSON logs to stdout |
| `CORS_ORIGINS` | localhost dev ports | Only needed when the frontend is on another origin |
| `WEB_CONCURRENCY` | `1` | Uvicorn workers (each runs its own sampler and scheduler) |
| `PUBLIC_DEMO` | `false` | Read-only registry, demo-only Playground, rate limits; for internet-facing demos |
| `PUBLIC_DEMO_SOURCE_URL` | empty | "Source code" link shown in the public-demo banner |
| `PUBLIC_DEMO_REQUESTS_PER_MINUTE` / `PUBLIC_DEMO_GLOBAL_REQUESTS_PER_MINUTE` | `10` / `60` | Playground runs per visitor IP / for everyone |
| `PUBLIC_DEMO_MAX_PROMPT_CHARS` / `PUBLIC_DEMO_MAX_TOKENS` | `4000` / `1024` | Input limits in a public demo |
| `PUBLIC_DEMO_KEPT_REQUESTS` | `5000` | Visitor runs kept in the database (oldest removed first) |
| `STATIC_DIR` | empty | Serve a built frontend from the API process (set by the root `Dockerfile`) |
| `BIND_ADDRESS`, `FRONTEND_PORT`, `BACKEND_PORT` | `127.0.0.1`, `8080`, `8000` | Compose port publishing |
| `VITE_API_BASE_URL` (frontend build arg) | empty | Absolute API origin when not served same-origin |

## Local development

Requirements: Python 3.12–3.14, Node 20.19+ or 22.12+, PostgreSQL 13+.
Run the commands below from the directories shown; the backend virtualenv lives in `backend/.venv`.

### 1. Start PostgreSQL

The backend's default connection is `postgresql://observatory:observatory@localhost:5432/observatory`.
Either option below creates exactly that, so no `.env` file is needed.

**Docker** (Docker Desktop must be running):

```bash
make dev-db      # = docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
```

**Homebrew on macOS** (no Docker):

```bash
brew install postgresql@16
brew services start postgresql@16        # also starts it at every login
"$(brew --prefix postgresql@16)/bin/psql" postgres \
  -c "CREATE ROLE observatory LOGIN PASSWORD 'observatory' CREATEDB;" \
  -c "CREATE DATABASE observatory OWNER observatory;"
```

**An existing server:** create a database and put its URL in `backend/.env`
(`cp .env.example backend/.env`, then set `DATABASE_URL=postgresql://user:password@host:5432/dbname`).

If the database is unreachable, the backend and Alembic stop with one line naming the host, port and
cause (for example, `Cannot connect to PostgreSQL at localhost:5432/observatory: connection refused`)
instead of a driver traceback.

### 2. Backend

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/alembic upgrade head
.venv/bin/uvicorn --factory app.main:create_app --reload --port 8000
```

### 3. Frontend (second terminal)

```bash
cd frontend
npm ci
npm run dev                    # http://localhost:5173, proxies /api to localhost:8000
```

### Maintenance commands

```bash
cd backend
.venv/bin/python -m app.cli reseed-demo   # regenerate labelled sample history now
.venv/bin/python -m app.cli purge-demo    # delete demo models and demo requests (set DEMO_MODE=false first)
# In Docker: docker compose exec backend python -m app.cli purge-demo
```

New migration after changing models: `alembic revision --autogenerate -m "describe change"`, review, then `alembic upgrade head`.

## Testing

```bash
cd backend
.venv/bin/pytest                               # uses observatory_test on the local server
.venv/bin/ruff check . && .venv/bin/ruff format --check .

cd ../frontend
npm test && npm run lint && npm run typecheck && npm run build
```

The backend suite runs against real PostgreSQL. By default it uses an `observatory_test` database on the
same server and with the same credentials as local development, and creates it on first run (the
`observatory` role from step 1 has `CREATEDB`). To use another database, set `TEST_DATABASE_URL`. Its name
must contain `test`, because every run drops and re-migrates all of its tables; the suite refuses any other name.

**Backend (119 tests, PostgreSQL 16):** model CRUD, validation, duplicate names, encrypted keys,
connection checks (healthy, auth failure, unreachable); inference through demo, OpenAI-compatible,
vLLM and Hugging Face providers with a mocked transport, covering exact and estimated tokens, upstream
HTTP errors, timeouts, malformed responses and disabled models; analytics percentiles against hand-computed
values, data-source filtering, time series, overview deltas; log search (including literal `%`), filters,
pagination and detail; infrastructure, GPU-unavailable reporting, vLLM metric scraping, Prometheus output,
request-ID handling, no GPU series exported without a GPU; clear startup and migration errors when the
database is unreachable; public-demo restrictions (read-only registry, demo-only inference, input limits,
rate limiting, bounded storage); single-container static serving, including SPA fallback and path traversal; demo seeding, reseeding and purging without touching real data; migrations
matching the ORM models.

**Frontend (35 tests, Vitest + Testing Library):** formatters, model-form validation and payloads,
stat-card deltas, and page-level interaction tests for the Model Registry, Playground, Request Logs and
Overview (demo labelling, data-source switching, error and retry states, public-demo banner and read-only
registry) against a mocked API.

## Security

- **No built-in authentication.** Anyone who can reach the dashboard can register endpoints and spend
  their tokens. Keep the default `127.0.0.1` binding, or put it behind an authenticating reverse proxy
  or VPN. [DEPLOYMENT.md](DEPLOYMENT.md#protecting-the-dashboard) has examples. For an internet-facing
  demo, `PUBLIC_DEMO=true` makes the registry read-only and limits the Playground to demo models.
- API keys are encrypted with Fernet using a key derived from `SECRET_KEY`, never logged and never returned.
- Production mode refuses the default or short `SECRET_KEY`.
- Endpoint URLs must be http(s) without embedded credentials. Outbound requests do not follow redirects,
  so an endpoint can't bounce the `Authorization` header to another host.
- Prompts and responses are stored in PostgreSQL and are not written to logs.
- nginx sends a strict Content-Security-Policy, `X-Frame-Options: DENY` and `nosniff`.
- Input limits: prompt 32k characters, system prompt 8k, `max_tokens` 1–8192, temperature 0–2,
  timeout 1–600 s.
- Containers run as non-root (backend) with health checks.

## Known limitations

- **No user accounts or RBAC**; see [Security](#security).
- **No streaming.** Responses are requested non-streamed, so time-to-first-token is not measured, and
  generation speed is completion tokens over end-to-end latency.
- **Host metrics describe the backend's machine.** psutil runs inside the backend container; CPU count and
  memory reflect the host kernel, not container cgroup limits. GPU metrics require the backend to run on
  the GPU host (`docker-compose.gpu.yml`); otherwise use vLLM `/metrics` scraping for remote GPU servers.
- **Utilisation history is in memory** (≈1 hour, per worker) and resets on restart. Use the `/metrics`
  endpoint with Prometheus for long-term retention.
- **Hugging Face token counts are estimated** because TGI does not report prompt tokens by default.
- **Token estimates** use ~4 characters/token and can be off by 20–30% for code or non-English text.
- **Log search uses `ILIKE`**, which scans text. For millions of rows, add a `pg_trgm` GIN index or ship
  logs to a search engine. There is no automatic retention policy for request history.
- **One process per background job.** With `WEB_CONCURRENCY > 1`, each worker runs its own sampler and
  health-check loop.
- **Demo models come back on restart** while `DEMO_MODE=true`. Set it to `false` and run `purge-demo`
  to remove them permanently.
- The CI workflow is included but was not executed as part of this build; see the verification notes in
  [DEPLOYMENT.md](DEPLOYMENT.md#verification-status).
