# Troubleshooting

## Diagnosing quickly

```bash
./scripts/healthcheck.sh                  # every component
curl -s localhost:8000/ready | jq         # which dependency is failing
docker compose logs -f api --tail=100     # backend logs
docker compose ps                         # container states
```

`/ready` names the failing component, and every error response carries an
`X-Request-ID` that appears in the logs.

---

## Startup

### `alembic upgrade head` fails

Confirm the database is reachable and the URL uses the async driver:

```bash
docker compose exec postgres pg_isready -U nvo -d nvo
echo $DATABASE_URL   # must be postgresql+asyncpg://…  not postgresql://
```

### API exits with `SECRET_KEY must be set`

Expected in staging and production. Generate one:

```bash
openssl rand -base64 48
```

### `startup_seed_failed` in the logs

The API started before the schema existed. Run `make migrate` (Compose does
this automatically via the `migrate` service; check whether it errored).

### No admin account exists

`BOOTSTRAP_ADMIN_PASSWORD` was unset, so the account was deliberately not
created — the platform ships no default credential. Create one:

```bash
python scripts/create_admin.py --email admin@example.com
```

---

## No data on the dashboard

### Every KPI shows `—`

This is correct behaviour when nothing was measured — the platform does not
invent values. Check, in order:

1. **Data source** — the header selector may be on Production while data is in Demo.
2. **Time range** — widen to 24h.
3. **Freshness** — the header shows sample age; "Stale" means collection stopped.
4. **Telemetry enabled** — `TELEMETRY_ENABLED=true`.

### `NVIDIA GPU unavailable`

Check the specific reason:

```bash
curl -s "localhost:8000/api/v1/gpus/availability?source=production" \
  -H "Authorization: Bearer $TOKEN" | jq
```

| Reason | Fix |
|---|---|
| `nvml_library_not_installed` | Install `nvidia-ml-py` in the runtime image |
| `nvml_init_failed` | No driver or GPU visible — check `nvidia-smi` on the host and the Container Toolkit |
| `no_nvidia_gpu_detected` | NVML initialised but found no devices; check `--gpus all` or the device plugin |
| `gpu_metrics_disabled` | Set `GPU_METRICS_ENABLED=true` |

Inside a container the most common cause is a missing Container Toolkit. Verify:

```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

### Demo Mode produces nothing

```bash
curl -s localhost:8000/api/v1/demo -H "Authorization: Bearer $TOKEN" | jq
```

`enabled` must be true and `running` must be true. If `samples_generated` is
zero, check the logs for `demo_tick_failed`. Force a backfill:

```bash
curl -X POST "localhost:8000/api/v1/demo/backfill?minutes=60&reset=true" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Authentication

### 401 on every request

Access tokens expire after 30 minutes. The frontend refreshes automatically; a
`curl` session must re-authenticate. If refresh also fails, the refresh token
was revoked (it rotates on use, and reuse revokes the family).

### 403 with a valid token

The role or key lacks the scope. Check `GET /api/v1/auth/me`, and see the scope
table in [SECURITY.md](SECURITY.md).

### API key rejected

Keys are shown once at creation and cannot be recovered. Confirm the key is
active in `GET /api/v1/auth/api-keys`, and note that keys are bound to
`SECRET_KEY` — changing it invalidates every existing key.

---

## Performance

### Slow dashboard queries

Dashboards read pre-aggregated rollups, so slowness usually means the
aggregation worker is not running. Check for `aggregation_cycle_failed` in the
logs and confirm `TELEMETRY_ENABLED=true`. Verify indexes exist:

```sql
SELECT indexname FROM pg_indexes WHERE tablename = 'inference_metrics';
```

### Database growing quickly

Check retention is sweeping:

```bash
curl -s localhost:8000/metrics | grep retention_rows_deleted
```

Reduce `RETENTION_RAW_DAYS`, or increase `TELEMETRY_INTERVAL_SECONDS` to sample
less often.

### 429 responses

Rate limiting is per credential. Raise `RATE_LIMIT_REQUESTS`, or issue separate
API keys per client so one noisy client cannot exhaust another's budget.

---

## AI agent

### Answers say "no language model was used"

Expected with `LLM_PROVIDER=none`. The deterministic engine produces the full
diagnosis; an LLM only adds narration. Set `LLM_PROVIDER` and `LLM_API_KEY` to
enable it.

### The agent refuses a question

Either the prompt guard matched an injection pattern, or the question was
off-topic. The response includes `refusal_reason`. Rephrase in terms of GPU,
inference, batching, cost or alert telemetry.

### The agent reports no data

It is being honest: no telemetry existed for the selected window and data
source. Widen the range or switch source.

---

## Frontend

### "Cannot reach the API"

`NEXT_PUBLIC_API_BASE_URL` is baked in **at build time**, not read at runtime.
If you changed it, rebuild:

```bash
docker compose build web --build-arg NEXT_PUBLIC_API_BASE_URL=http://your-host:8000
```

### CORS errors in the browser console

Add the exact dashboard origin (scheme, host and port) to `CORS_ORIGINS` and
restart the API.

### WebSocket will not connect

The dashboard falls back to polling automatically, so this degrades rather than
breaks. Behind a proxy, ensure upgrade headers pass through — the sample
ingress sets `nginx.ingress.kubernetes.io/websocket-services`.

---

## Kubernetes

### Pods in `CrashLoopBackOff`

```bash
kubectl -n nvo logs deploy/nvo-api --previous
kubectl -n nvo describe pod -l app.kubernetes.io/name=nvo-api
```

Most often a missing secret key or an unreachable database.

### Pod runs but is never Ready

`/ready` checks the database while `/health` does not, so this pattern means
the process is alive but cannot reach PostgreSQL. Verify `DATABASE_URL` in the
secret and that network policy permits port 5432.

### The telemetry DaemonSet schedules nowhere

It targets `nvidia.com/gpu.present=true`. Label the nodes:

```bash
kubectl get nodes -l nvidia.com/gpu.present=true
kubectl label node <node> nvidia.com/gpu.present=true
```

---

## Getting help

Include when reporting an issue:

```bash
curl -s localhost:8000/health | jq              # version and environment
curl -s localhost:8000/ready | jq               # component health
docker compose logs api --tail=50               # recent logs
```

Plus the `X-Request-ID` of a failing request — it correlates the response with
its server-side log entries.
