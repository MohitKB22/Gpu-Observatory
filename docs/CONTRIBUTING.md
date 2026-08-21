# Contributing

## Setup

```bash
make setup      # backend virtualenv + frontend dependencies
make env        # create .env from the example
make migrate    # apply migrations
make verify     # everything CI runs
```

## Workflow

1. Branch from `develop`: `feat/…`, `fix/…`, `docs/…`, `refactor/…`, `test/…`
2. Make the change with tests.
3. `make verify` must pass locally before opening a pull request.
4. Open the PR against `develop` describing what changed and why.

## Standards

### Python

- Ruff and Black at 100 columns (`make format`).
- Type hints on public functions; MyPy must pass.
- Docstrings explain *why*, not *what* — the code already says what.
- Services return domain objects; routers own HTTP concerns only.
- Never swallow an exception silently. Log it with context, or let it surface.

### TypeScript

- Strict mode, including `noUncheckedIndexedAccess`. No `any`.
- Server state belongs in TanStack Query; only UI selections go in Zustand.
- Every data surface renders loading, empty, error and success states.
- Format a missing value as `—` via `lib/format`, never as `0`.

### Tests

Assert the guarantee, not the mechanism, and say so in the assertion message:

```python
assert all(k["value"] is None for k in body["kpis"]), (
    "with no telemetry every KPI must be null rather than an invented number"
)
```

## Invariants

These are the properties the platform exists to uphold. A change that weakens
one will be rejected.

1. **No fabricated measurements.** If it was not measured, it is `null`.
2. **Demo data stays quarantined.** New telemetry tables carry `data_source`,
   and new read paths filter on it.
3. **Diagnosis works without an LLM.** New analysis belongs in the rules
   engine, not in a prompt.
4. **The agent gains no write capability.** New tools are read-only.
5. **Cost is always labelled an estimate.**

## Adding features

**A diagnostic rule** — add a pure function to
`app/services/diagnostics/rules.py` taking `DiagnosticContext` and returning
`list[Finding]`; register it in `ALL_RULES`; add a test that fires it from
seeded telemetry and a test that it stays silent on a healthy window.

**An API endpoint** — schema in `app/schemas/`, logic in `app/services/`, route
in `app/api/v1/`, scope dependency, test covering success, validation failure
and authorisation failure.

**A dashboard page** — route under `apps/web/app/`, query hook in
`hooks/useQueries.ts`, all four states, and a nav entry in `Sidebar.tsx`.

**A model change** — edit the model, run `make migration m="…"`, review the
generated SQL by hand, verify `upgrade` then `downgrade` then `upgrade`.

## Review criteria

- Does it hold the five invariants?
- Are all four UI states handled?
- Do the tests assert behaviour rather than implementation?
- Are errors handled explicitly, with context?
- Would a new engineer understand *why* from the comments?
