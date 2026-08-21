# Security

## Authentication

Two credential types, one header (`Authorization: Bearer <token>`).

**JWT for humans.** Argon2id password hashing (`time_cost=2`,
`memory_cost=64 MiB`, `parallelism=2`). Access tokens default to 30 minutes.
Refresh tokens are stored server-side as SHA-256 hashes so they can be revoked,
and rotate on every use — presenting a revoked refresh token revokes the whole
family, on the assumption it was stolen.

**API keys for machines.** Format `nvo_{live|test}_{32 bytes urlsafe}`. Only a
**keyed HMAC-SHA256** is persisted, so a leaked database alone does not permit
offline verification of guesses without also leaking `SECRET_KEY`. The
plaintext is returned exactly once, at creation.

**Account protection.** Five consecutive failures lock an account for 15
minutes. Login returns an identical error and comparable timing for unknown
accounts and wrong passwords, so the endpoint cannot be used to enumerate
users. Password hashes are transparently upgraded when parameters change.

## Authorisation

| Role | Scopes |
|---|---|
| `viewer` | `telemetry:read`, `models:read`, `alerts:read`, `diagnostics:read`, `cost:read` |
| `operator` | viewer + `telemetry:write`, `models:write`, `alerts:write`, `diagnostics:run`, `agent:chat` |
| `admin` | all, including `admin` |

Scopes are enforced per-route by dependency, not by convention. API keys carry
an explicit scope list which may be narrower than any role, and unknown scopes
are **rejected at creation** rather than silently dropped.

## Secrets

- `SECRET_KEY` is **required** in staging and production — startup fails
  without it. Local and test environments generate an ephemeral key.
- `DEBUG=true` is rejected in production.
- `.env` is gitignored; only `.env.example` with placeholders is committed.
- Kubernetes secrets are referenced, never templated with real values. The
  chart documents creating them out-of-band; `02-secret.example.yaml` is
  excluded from the kustomization.
- No default administrator password exists. If `BOOTSTRAP_ADMIN_PASSWORD` is
  unset the account is not created and a warning is logged.
- CI runs `gitleaks` on every push.

## Transport and headers

Applied to every response:

| Header | Value |
|---|---|
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `no-referrer` |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |
| `Cross-Origin-Opener-Policy` | `same-origin` |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` (production only) |

CORS is an explicit allow-list from `CORS_ORIGINS` — never a wildcard.

## Rate limiting

Fixed-window, bucketed by a SHA-256 digest of the credential (never the
credential itself), or by client IP when anonymous. Backed by Redis when
available, with an in-process fallback. Health and metrics endpoints are exempt
so monitoring never trips the limiter. On a cache outage the limiter fails
open, deliberately: an observability platform going dark is worse than a
briefly unenforced limit.

## Input handling

- Pydantic v2 validates every request; unknown fields are ignored and bounds
  are enforced on all numeric and string fields.
- Bodies above `MAX_REQUEST_BODY_BYTES` (default 1 MiB) are rejected before
  buffering.
- All database access uses parameterised SQLAlchemy expressions — no string
  interpolation anywhere.
- Validation errors are sanitised: the 422 response reports location, message
  and type, but **never echoes the submitted value**, so a mistyped secret does
  not appear in a log or an error body.

## Error hygiene

One error envelope for every failure. Internal details — tracebacks, SQL,
driver messages, file paths — are logged with a request ID but never returned
to the caller. Tests assert that error bodies contain none of `traceback`,
`sqlalchemy`, `site-packages`, or `select `.

## AI agent boundaries

The agent's safety rests on capability, not instruction.

- **No dangerous tool exists.** The registry contains eleven read-only queries.
  There is no tool to execute a command, write to the database, modify
  configuration, or read secrets.
- `invoke()` refuses unknown tool names rather than guessing, and re-checks the
  read-only flag as defence in depth.
- A prompt guard screens for instruction override, role hijack, system-prompt
  exfiltration, secret exfiltration, code execution, SQL injection, data
  mutation and configuration mutation.
- Tool output is truncated before entering model context; caller-supplied time
  ranges are clamped to supported presets.
- Recommendations are advisory. The agent cannot apply a change.

## Audit logging

Append-only records for authentication, user and key lifecycle, alert
acknowledgement and resolution, model and deployment changes, and demo control.
Each entry carries actor, action, resource, outcome, request ID and source IP.
Audit writes use an independent session so a failed business transaction still
leaves a trail, and an audit failure never breaks the request path.

## Container and cluster hardening

- Multi-stage builds; build toolchains never reach the runtime image.
- Non-root user (uid 10001) in every image, verified in CI.
- `readOnlyRootFilesystem: true`, `allowPrivilegeEscalation: false`, all
  capabilities dropped, `seccompProfile: RuntimeDefault`.
- Namespace enforces the `restricted` Pod Security Standard.
- Default-deny ingress NetworkPolicy, then explicit allows for the paths the
  platform needs.
- `automountServiceAccountToken: false` — no workload needs the API server.

## Dependency management

CI runs Trivy (filesystem, CRITICAL/HIGH), `pip-audit`, and
`npm audit --audit-level=high`. Dependencies are pinned to exact versions in
both `requirements.txt` and `package.json`.

## Reporting a vulnerability

Report privately to the maintainers rather than opening a public issue. Include
affected version, reproduction steps and impact.

## Production checklist

- [ ] `SECRET_KEY` set to 48+ random bytes, unique per environment
- [ ] `BOOTSTRAP_ADMIN_PASSWORD` set, then the account's password rotated
- [ ] `AUTH_ENABLED=true`
- [ ] `DEMO_MODE=false`
- [ ] `DEBUG=false` and `ENVIRONMENT=production`
- [ ] `CORS_ORIGINS` restricted to real dashboard origins
- [ ] TLS terminated at the ingress with HSTS
- [ ] Database and Redis credentials unique and rotated
- [ ] Network policies applied
- [ ] API keys scoped to the minimum each client needs
- [ ] Audit log retention configured
