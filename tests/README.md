# Cross-cutting tests

Application test suites live beside the code they exercise:

- Backend — `apps/api/tests/` (180 tests)
- Frontend — `apps/web/tests/` (31 tests)

See [docs/TESTING.md](../docs/TESTING.md) for the strategy and how to run them.

This directory holds cross-cutting checks that span both applications and
therefore belong to neither. `scripts/healthcheck.sh` verifies a running stack
end to end and is used both locally and after deployment:

```bash
./scripts/healthcheck.sh
```
