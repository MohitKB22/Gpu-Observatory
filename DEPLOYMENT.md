# Deployment guide

- [Single host with Docker Compose](#single-host-with-docker-compose)
- [Going to production](#going-to-production)
- [Protecting the dashboard](#protecting-the-dashboard)
- [GPU hosts](#gpu-hosts)
- [Deploying frontend and backend separately](#deploying-frontend-and-backend-separately)
- [PostgreSQL](#postgresql)
- [Connecting real inference endpoints](#connecting-real-inference-endpoints)
- [Prometheus](#prometheus)
- [Operations](#operations)
- [Verification status](#verification-status)

## Single host with Docker Compose

```bash
cp .env.example .env     # optional for local use; required to change production settings
docker compose up --build -d
docker compose ps        # db, backend and frontend should all report "healthy"
```

| Service | Image | Notes |
|---|---|---|
| `db` | `postgres:16-alpine` | Data in the `postgres-data` volume |
| `backend` | built from `backend/Dockerfile` | Runs `alembic upgrade head` (with retries) on start, then uvicorn on :8000 |
| `frontend` | built from `frontend/Dockerfile` | nginx serving the React build on :80 and proxying `/api` to the backend |

Start order is enforced with health checks: db → backend (`/api/health`) → frontend.

## Going to production

Set these in `.env`:

```bash
APP_ENV=production
SECRET_KEY=<output of: openssl rand -hex 32>   # keep it; changing it invalidates stored API keys
DEMO_MODE=false
POSTGRES_PASSWORD=<strong password>
LOG_FORMAT=json
```

Then remove demo data that an earlier demo run created:

```bash
docker compose up -d --build
docker compose exec backend python -m app.cli purge-demo
```

With `DEMO_MODE=false`, analytics default to **Real only**. Demo data can still be viewed explicitly if any
remains.

## Protecting the dashboard

The application has **no login**. Anyone who can reach it can register endpoints, run inference with the
stored credentials, and read prompts and responses. Choose one of:

1. **Keep it private** (default): ports bind to `127.0.0.1`; reach it over SSH tunnelling or a VPN
   (`ssh -L 8080:localhost:8080 server`).
2. **Authenticating reverse proxy** in front of the frontend container. For example, Caddy with basic auth
   and automatic TLS:

   ```caddyfile
   observatory.example.com {
       basic_auth {
           admin <hash from: caddy hash-password>
       }
       reverse_proxy 127.0.0.1:8080
   }
   ```

   For SSO, use oauth2-proxy, Cloudflare Access, Tailscale Serve or your ingress controller's auth.
3. Only set `BIND_ADDRESS=0.0.0.0` when one of the above protects the ports.

Leave `BACKEND_PORT` unpublished (or bound to localhost) in production unless Prometheus needs it; the
frontend container already proxies `/api` internally.

## GPU hosts

To report GPU utilisation, memory, temperature and power, the backend must run on the GPU machine with the
NVIDIA driver and [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build -d
```

The override gives the backend container the `utility` capability, which mounts NVML. Check it with
`GET /api/infrastructure` → `gpu.available: true, gpu.source: "nvml"`. Without a driver, the GPU section
reports why it is unavailable instead of showing numbers.

The dashboard itself never needs a GPU. Inference usually runs elsewhere: register a remote vLLM server and
the Infrastructure page shows its running/waiting requests and KV-cache usage from its `/metrics`.

## Deploying frontend and backend separately

### Backend (any container platform: Kubernetes, ECS, Cloud Run, Fly.io, Render, Railway, …)

Build `backend/Dockerfile`. Configure:

| Setting | Value |
|---|---|
| Port | `8000` (or set `PORT`) |
| Health check | `GET /api/health` |
| `DATABASE_URL` | Managed PostgreSQL URL (see below) |
| `APP_ENV`, `SECRET_KEY`, `DEMO_MODE` | As in [Going to production](#going-to-production) |
| `CORS_ORIGINS` | The frontend's origin, if it is served from a different domain |
| `RUN_MIGRATIONS` | `true` (default) runs `alembic upgrade head` at start. With many replicas, set `false` and run migrations once as a release step: `alembic upgrade head` |
| `WEB_CONCURRENCY` | Keep `1` per container and scale with replicas |

Each replica runs its own background health checks and sampler. That is harmless (checks are cheap and
idempotent), but with many replicas you may want `HEALTH_CHECK_INTERVAL_SECONDS` higher on all but one.

### Frontend, option A: the nginx image (recommended)

Build `frontend/Dockerfile` and set `BACKEND_URL` to the backend's internal URL
(e.g. `http://observatory-backend:8000`). The browser only talks to one origin, so no CORS is needed.

### Frontend, option B: static hosting (Vercel, Netlify, S3 + CloudFront, …)

```bash
cd frontend
VITE_API_BASE_URL=https://api.observatory.example.com npm run build   # output: dist/
```

- Configure an SPA fallback (all unknown paths → `/index.html`).
- Set `CORS_ORIGINS=https://observatory.example.com` on the backend.
- If you copy the nginx security headers, add the API origin to the CSP `connect-src`.

## PostgreSQL

Any PostgreSQL 13+ works (the app uses `percentile_cont` and `FILTER`, available since 9.4; tested on 16).

```bash
DATABASE_URL=postgresql://user:password@host:5432/observatory
DATABASE_URL=postgresql://user:password@host:5432/observatory?sslmode=require   # managed services
```

`postgres://` and `postgresql://` URLs are rewritten to the psycopg 3 driver automatically. Migrations:

```bash
docker compose exec backend alembic upgrade head      # or: cd backend && alembic upgrade head
docker compose exec backend alembic current
```

## Connecting real inference endpoints

Register endpoints in **Model Registry → Register model**, click **Check connection**, then use the
Playground.

**OpenAI or any OpenAI-compatible API**: provider *OpenAI-compatible*, URL `https://api.openai.com/v1`,
model `gpt-4o-mini`, API key `sk-…`.

**vLLM on a GPU server**:

```bash
# On the GPU server
docker run --gpus all -p 8000:8000 vllm/vllm-openai:latest \
  --model meta-llama/Llama-3.1-8B-Instruct --api-key "$VLLM_API_KEY"
```

Register with provider *vLLM*, URL `http://<gpu-server>:8000/v1`, model
`meta-llama/Llama-3.1-8B-Instruct` and the same API key. Its `/metrics` is scraped for the Infrastructure page.

**Hugging Face**: provider *Hugging Face*, URL of the Inference Endpoint (or
`https://api-inference.huggingface.co/models/<repo>`), API key = HF access token. For HF's
OpenAI-compatible router, use provider *OpenAI-compatible* with `https://router.huggingface.co/v1`.

**Endpoints on the Docker host** (Ollama, LM Studio, a local vLLM): inside the backend container,
`localhost` is the container itself. Use `http://host.docker.internal:<port>/v1`; the compose file maps
that name on Linux too.

Per-model **timeout** (1–600 s) bounds each request; failures are recorded with their kind (`timeout`,
`connection`, `auth`, `http`, `invalid_response`, `configuration`).

## Prometheus

```yaml
scrape_configs:
  - job_name: ai-inference-observatory
    metrics_path: /metrics
    static_configs:
      - targets: ["observatory-backend:8000"]
```

Exported series include `observatory_inference_requests_total{model,provider,status,demo}`,
`observatory_inference_latency_seconds` (histogram), `observatory_inference_tokens_total{kind,counted}`,
`observatory_model_up`, `observatory_host_cpu_percent`, `observatory_host_memory_percent`, and per-GPU
`observatory_gpu_utilization_percent{gpu}` / `observatory_gpu_memory_used_bytes{gpu}`. The GPU series only
exist once a real reading has been taken, so a host without a GPU never reports "0%". Filter
`demo="false"` in alerts.

## Operations

| Task | Command |
|---|---|
| Logs (JSON, one object per line) | `docker compose logs -f backend` |
| Backup | `docker compose exec db pg_dump -U observatory observatory > backup.sql` |
| Restore | `docker compose exec -T db psql -U observatory observatory < backup.sql` |
| Upgrade | `git pull && docker compose up -d --build` (migrations run on start) |
| Refresh demo sample data | `docker compose exec backend python -m app.cli reseed-demo` |
| Remove demo data | `docker compose exec backend python -m app.cli purge-demo` |
| Rotate `SECRET_KEY` | Change it, restart, then re-enter each model's API key (old ciphertexts can't be decrypted; affected models report a configuration error) |

Every HTTP response carries an `X-Request-ID` (the caller's, if it is safe, otherwise generated), which also
appears in the backend's request log line.

## Verification status

What was executed while building this release, and what was not:

| Check | Result |
|---|---|
| Backend tests against PostgreSQL 16 | 102 passed on Python 3.12 (the Docker image's version), 3.13 and 3.14 |
| Local-development path (Homebrew-style role and database, default settings, no `.env`) | migrations and the full test suite run with no environment variables; the test database is created automatically |
| Backend lint/format (ruff) | clean |
| Alembic upgrade → downgrade → upgrade on PostgreSQL 16 | passed; a test confirms migrations match the ORM |
| Backend image steps (fresh Python 3.12 env, `requirements.txt` only, real `docker-entrypoint.sh` against an empty database, Dockerfile HEALTHCHECK command) | passed |
| Frontend tests (Vitest) | 32 passed |
| Frontend typecheck (strict), ESLint, production build | clean |
| Frontend image steps (clean `npm ci` + `npm run build`) | passed |
| nginx config (template rendered as the nginx image does, `nginx -t`, SPA routing, `/api` proxy, headers, asset caching) | passed |
| Browser end-to-end walk through all six modules in headless Chrome, via nginx with the CSP enforced, desktop and 390 px mobile | passed, no console errors, no horizontal scroll on mobile |
| `docker compose config` (base and GPU override) | valid |
| **`docker compose up --build` itself** | **Not executed.** The build environment's network policy blocked all container registries (Docker Hub, GCR mirror, ECR Public), so base images could not be pulled. Every step inside the images was run natively instead (rows above). |
| GitHub Actions workflow | Included, not run |
| Real GPU telemetry (NVML / nvidia-smi) | Not exercised: no GPU in the build environment. Parsing is unit-tested; the "unavailable" path was verified live. |
| Live third-party endpoints (OpenAI, HF, vLLM) | Not called (no credentials). Provider request/response handling is tested against recorded payload shapes with a mock transport; a real connection failure was verified live in the browser. |
