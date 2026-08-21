# config

Shared configuration conventions.

Configuration is environment-driven and validated at startup by
`apps/api/app/core/config.py` (Pydantic Settings). `.env.example` at the
repository root is the single reference for every supported variable.

Validation rules enforced at startup:

- `SECRET_KEY` is required in `staging` and `production`; startup fails without it.
- `DEBUG=true` is rejected in `production`.
- `LOG_LEVEL` must be a recognised level.
- Local and test environments generate an ephemeral secret so a developer is
  never blocked, and tokens simply do not survive a restart.

Precedence: process environment → `.env` → defaults in `Settings`.
