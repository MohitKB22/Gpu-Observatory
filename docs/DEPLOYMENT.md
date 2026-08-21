# Deployment

## Docker Compose

```bash
cp .env.example .env
# Required: SECRET_KEY, BOOTSTRAP_ADMIN_PASSWORD
docker compose up -d --build
./scripts/healthcheck.sh
```

Nine services start: PostgreSQL, Redis, a one-shot migration job, the API, the
frontend, the inference gateway, Prometheus, Grafana, and (under the `gpu`
profile) the telemetry agent.

Migrations run as a dedicated `migrate` service that the API waits on via
`service_completed_successfully`, so the schema is always current before the
API starts.

| Service | Port | Purpose |
|---|---|---|
| web | 3000 | Dashboard |
| api | 8000 | REST, WebSocket, `/metrics` |
| inference-gateway | 8080 | Instrumented inference proxy |
| postgres | 5432 | Primary store |
| redis | 6379 | Cache and rate limiting |
| prometheus | 9090 | Metrics |
| grafana | 3001 | Dashboards |

### Enabling real GPU telemetry

The base stack deliberately requires no NVIDIA hardware. To use real GPUs:

**1. Install the NVIDIA Container Toolkit**

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

**2. Verify**

```bash
docker run --rm --gpus all nvidia/cuda:12.4.0-base-ubuntu22.04 nvidia-smi
```

**3. Mint an agent credential and start with the GPU profile**

```bash
python scripts/create_api_key.py --name telemetry-agent \
  --scopes telemetry:read telemetry:write

DEMO_MODE=false AGENT_API_KEY=nvo_live_... docker compose --profile gpu up -d
```

Verify collection:

```bash
curl -s "http://localhost:8000/api/v1/gpus/availability?source=production" \
  -H "Authorization: Bearer $TOKEN" | jq
# expect: "nvml_available": true, "gpu_count": <n>
```

## Kubernetes

### Kustomize

```bash
kubectl apply -k infra/kubernetes/base
```

Creates the namespace (Pod Security `restricted`), ConfigMap, API deployment
with an `alembic upgrade head` initContainer, frontend, inference gateway,
telemetry DaemonSet, dependency StatefulSets, network policies and ingress.

Secrets are **not** created — the example manifest is excluded from the
kustomization on purpose:

```bash
kubectl -n nvo create secret generic nvo-secrets \
  --from-literal=SECRET_KEY="$(openssl rand -base64 48)" \
  --from-literal=DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/nvo' \
  --from-literal=REDIS_URL='redis://host:6379/0' \
  --from-literal=BOOTSTRAP_ADMIN_PASSWORD='<strong-password>'

kubectl -n nvo create secret generic nvo-agent-credentials \
  --from-literal=NVO_API_KEY='nvo_live_...'
```

### Helm

```bash
helm install nvo infra/helm/nvidia-ai-performance-observatory \
  --namespace nvo --create-namespace \
  --set ingress.host=observatory.example.com \
  --set image.registry=ghcr.io/your-org \
  --set telemetryAgent.enabled=true \
  --set serviceMonitor.enabled=true
```

Key values:

| Value | Default | Notes |
|---|---|---|
| `api.replicaCount` | 3 | Ignored when autoscaling is enabled |
| `api.autoscaling.enabled` | `true` | 3–12 replicas on CPU and memory |
| `api.migrations.enabled` | `true` | Runs migrations as an initContainer |
| `telemetryAgent.enabled` | `false` | Enable on clusters with NVIDIA hardware |
| `config.demoMode` | `false` | Never enable in production |
| `postgresql.enabled` | `false` | Prefer a managed database |
| `serviceMonitor.enabled` | `false` | Requires the Prometheus Operator CRDs |

### Scaling and availability

- **API**: HPA 3–12 on 70% CPU / 80% memory; PDB `minAvailable: 2`;
  topology spread across nodes; `maxUnavailable: 0` during rollout.
- **Frontend**: HPA 2–6 on 75% CPU; PDB `minAvailable: 1`.
- **Telemetry agent**: DaemonSet on `nvidia.com/gpu.present=true` with a
  `nvidia.com/gpu` toleration.

Probes: `startupProbe` allows up to two minutes for first boot (Demo Mode
backfill can be slow), `livenessProbe` hits `/health` (no dependencies), and
`readinessProbe` hits `/ready` (checks the database), so a pod with a broken
database is removed from the Service without being killed.

### GPU node prerequisites

- NVIDIA drivers (or the GPU Operator)
- NVIDIA device plugin
- Nodes labelled `nvidia.com/gpu.present=true`
- Optionally `dcgm-exporter` — set `config.dcgmEnabled=true` and point
  `config.dcgmEndpoint` at it

## Production checklist

**Before**

- [ ] Images built and pushed for the target architecture
- [ ] Secrets created out-of-band
- [ ] `DEMO_MODE=false`, `AUTH_ENABLED=true`, `ENVIRONMENT=production`
- [ ] `CORS_ORIGINS` set to real origins
- [ ] Managed PostgreSQL and Redis provisioned with backups
- [ ] TLS certificate issued

**After**

- [ ] `/ready` returns 200 with all components healthy
- [ ] `/metrics` is scraped by Prometheus
- [ ] Grafana dashboards render
- [ ] Sign in with the bootstrap admin, then rotate its password
- [ ] Mint scoped API keys for agents and gateways
- [ ] Confirm `gpus/availability` reports `nvml_available: true` on GPU nodes
- [ ] Alert rules reviewed for your thresholds
- [ ] Pricing profile set to the rate you actually pay

## Backups

```bash
pg_dump -Fc -d "$DATABASE_URL" -f nvo-$(date +%F).dump   # backup
pg_restore -d "$DATABASE_URL" --clean nvo-2026-08-14.dump # restore
```

Redis holds only cache and rate-limit state and does not require backup.

## Upgrades

1. Review migrations in the release.
2. Back up the database.
3. Deploy — migrations run automatically as an initContainer.
4. Watch the rollout: `kubectl -n nvo rollout status deploy/nvo-api`.
5. Roll back with `kubectl rollout undo` if `/ready` does not recover.

Migrations are additive within a minor version, so a rollback of application
code does not require a schema downgrade.
