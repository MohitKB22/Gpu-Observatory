# API Reference

Base URL: `http://localhost:8000` · Interactive docs: `/docs` · Schema: `/openapi.json`

## Authentication

Two credential types share one `Authorization: Bearer <token>` header.

**JWT (human users)** — obtained from `POST /api/v1/auth/login`. Access tokens
last 30 minutes by default; refresh tokens rotate on use and the presented
token is revoked. Reuse of a revoked refresh token revokes the entire family,
on the assumption it was stolen.

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@localhost","password":"..."}' | jq -r .access_token)

curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/gpus
```

**API keys (machines)** — created by an admin, prefixed `nvo_live_` or
`nvo_test_`. Only a keyed HMAC of the key is stored; the plaintext is shown once
at creation.

```bash
curl -H "Authorization: Bearer nvo_live_xxx" http://localhost:8000/api/v1/gpus
```

## Roles and scopes

| Role | Scopes |
|---|---|
| `viewer` | `telemetry:read`, `models:read`, `alerts:read`, `diagnostics:read`, `cost:read` |
| `operator` | viewer + `telemetry:write`, `models:write`, `alerts:write`, `diagnostics:run`, `agent:chat` |
| `admin` | all scopes including `admin` |

API keys carry an explicit scope list, which may be narrower than any role.

## Conventions

**Data source.** Read endpoints accept `?source=production|demo`. Omitted, it
defaults to the server's configured mode. Namespaces never mix.

**Time ranges.** `?range=` accepts `5m`, `15m`, `1h`, `6h`, `24h`, `7d`, or an
explicit `start`/`end` pair (ISO 8601, max 90 days). Bucket width is chosen
automatically to keep any series under ~720 points.

**Pagination.** `?limit=` (1–1000, default 100) and `?offset=`. Responses:

```json
{ "items": [...], "meta": { "total": 1240, "limit": 100, "offset": 0, "has_more": true } }
```

**Errors.** Every error uses one envelope:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "details": { "errors": [...] },
    "request_id": "1f3c…"
  }
}
```

| Status | Code | Meaning |
|---|---|---|
| 400 | `app_error` | Malformed request |
| 401 | `unauthenticated` | Missing, invalid or expired credential |
| 403 | `forbidden` | Authenticated but lacking the required scope |
| 404 | `not_found` | No such resource in this data source |
| 409 | `conflict` | Duplicate, or an invalid state transition |
| 413 | `payload_too_large` | Body above `MAX_REQUEST_BODY_BYTES` |
| 422 | `validation_error` | Schema validation failed |
| 429 | `rate_limited` | Rate limit exceeded; see `Retry-After` |
| 502 | `upstream_error` | An inference backend failed |
| 503 | `database_error` / `service_unavailable` | Dependency unavailable |

Every response carries `X-Request-ID` (echoed from the request when supplied)
and `X-Response-Time-Ms`.

## Endpoints

### Operations

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | none | Liveness; never touches dependencies |
| GET | `/live` | none | Alias for Kubernetes |
| GET | `/ready` | none | Readiness; 503 when the database is unreachable |
| GET | `/metrics` | none | Prometheus text exposition |

### Authentication

| Method | Path | Scope | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | none | Issue a token pair |
| POST | `/api/v1/auth/refresh` | none | Rotate a refresh token |
| POST | `/api/v1/auth/logout` | none | Revoke a refresh token |
| GET | `/api/v1/auth/me` | any | Current user |
| GET | `/api/v1/auth/config` | none | Whether auth is enabled |
| POST | `/api/v1/auth/users` | admin | Create a user |
| GET | `/api/v1/auth/users` | admin | List users |
| PATCH | `/api/v1/auth/users/{id}` | admin | Update a user |
| POST | `/api/v1/auth/api-keys` | admin | Mint an API key |
| GET | `/api/v1/auth/api-keys` | admin | List keys (never the plaintext) |
| DELETE | `/api/v1/auth/api-keys/{id}` | admin | Revoke a key |
| GET | `/api/v1/auth/audit` | admin | Audit log |

### Telemetry

| Method | Path | Scope | Description |
|---|---|---|---|
| GET | `/api/v1/gpus` | `telemetry:read` | Registered devices |
| GET | `/api/v1/gpus/availability` | `telemetry:read` | NVML/DCGM availability and the reason if absent |
| GET | `/api/v1/gpus/{id}` | `telemetry:read` | Device, latest sample, processes, freshness |
| GET | `/api/v1/gpus/{id}/metrics` | `telemetry:read` | Raw samples, paginated and sortable |
| GET | `/api/v1/gpus/series/timeseries` | `telemetry:read` | Bucketed series; `?metrics=` selects fields |
| GET | `/api/v1/system/metrics` | `telemetry:read` | Latest host metrics |
| GET | `/api/v1/system/series` | `telemetry:read` | Bucketed host series |
| POST | `/api/v1/telemetry/ingest` | `telemetry:write` | Agent ingestion |
| GET | `/api/v1/overview` | `telemetry:read` | Dashboard KPIs |

### Models and inference

| Method | Path | Scope | Description |
|---|---|---|---|
| GET | `/api/v1/models` | `models:read` | Registry; supports `search`, `framework`, `sort`, `order` |
| POST | `/api/v1/models` | `models:write` | Register a model |
| GET | `/api/v1/models/{id}` | `models:read` | Model profile |
| PATCH | `/api/v1/models/{id}` | `models:write` | Update a model |
| GET | `/api/v1/models/{id}/performance` | `models:read` | Measured performance rollup |
| GET | `/api/v1/deployments` | `models:read` | Deployments |
| POST | `/api/v1/deployments` | `models:write` | Create a deployment |
| GET | `/api/v1/inference/metrics` | `telemetry:read` | Percentiles, throughput, tokens, batching |
| GET | `/api/v1/inference/latency` | `telemetry:read` | Histogram, clipped at P99 |
| GET | `/api/v1/inference/series` | `telemetry:read` | Bucketed inference series |
| GET | `/api/v1/inference/requests` | `telemetry:read` | Request table; `errors_only` filter |
| POST | `/api/v1/inference/requests` | `telemetry:write` | Gateway ingestion (≤1000 per call) |
| GET | `/api/v1/batches` | `telemetry:read` | Batching analytics and under/over-batching flags |
| GET | `/api/v1/comparisons/models` | `models:read` | Comparison of 2–6 models |

### Analytics

| Method | Path | Scope | Description |
|---|---|---|---|
| GET | `/api/v1/anomalies` | `diagnostics:read` | Detected anomalies |
| POST | `/api/v1/anomalies/scan` | `diagnostics:run` | Force a scan |
| GET | `/api/v1/alerts` | `alerts:read` | Alerts, filterable by state and severity |
| GET | `/api/v1/alerts/summary` | `alerts:read` | Counts by state and severity |
| POST | `/api/v1/alerts/{id}/acknowledge` | `alerts:write` | Acknowledge |
| POST | `/api/v1/alerts/{id}/resolve` | `alerts:write` | Resolve |
| POST | `/api/v1/alerts/evaluate` | `alerts:write` | Force evaluation |
| GET/POST/DELETE | `/api/v1/alert-rules` | `alerts:*` | Manage rules |
| POST | `/api/v1/diagnostics` | `diagnostics:run` | Run a diagnosis |
| GET | `/api/v1/diagnostics/history` | `diagnostics:read` | Past diagnoses |
| GET | `/api/v1/cost` | `cost:read` | Cost estimate |
| GET/POST | `/api/v1/cost/pricing` | `cost:read` / `alerts:write` | Pricing profiles |
| POST | `/api/v1/agent/chat` | `agent:chat` | Ask the Copilot |
| GET | `/api/v1/agent/capabilities` | `diagnostics:read` | Provider status and tool list |

### Demo and workloads

| Method | Path | Scope | Description |
|---|---|---|---|
| GET | `/api/v1/demo` | `telemetry:read` | Demo state |
| GET | `/api/v1/demo/scenarios` | `telemetry:read` | The seven scenarios |
| POST | `/api/v1/demo/scenario` | `telemetry:write` | Switch scenario |
| POST | `/api/v1/demo/backfill` | `telemetry:write` | Seed history |
| DELETE | `/api/v1/demo/data` | `telemetry:write` | Clear demo data only |
| GET/POST | `/api/v1/workloads` | `telemetry:*` | List and start workloads |
| GET | `/api/v1/workloads/profiles` | `telemetry:read` | The six load profiles |
| POST | `/api/v1/workloads/{id}/cancel` | `telemetry:write` | Cancel a run |

### WebSocket

```
ws://localhost:8000/ws/telemetry?token=<jwt-or-api-key>&channels=telemetry,alerts&source=demo
```

Browsers cannot set headers on a WebSocket handshake, so the credential is
passed as a query parameter. Channels: `telemetry`, `alerts`, `diagnostics`.
A snapshot is pushed every five seconds; send `ping` to receive `pong`. Clients
that cannot hold a socket open should poll the equivalent REST endpoints — the
dashboard degrades to polling automatically.

## Rate limiting

Fixed-window, bucketed by credential digest (or client IP when anonymous).
Defaults to 300 requests per 60 seconds. `/health`, `/ready`, `/live` and
`/metrics` are exempt so monitoring never trips the limiter. Responses carry
`X-RateLimit-Limit` and `X-RateLimit-Remaining`; a 429 carries `Retry-After`.
