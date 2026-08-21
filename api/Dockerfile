# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------- builder ---
FROM python:3.11-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Build tooling is needed for wheels that lack manylinux builds; it is left
# behind in this stage rather than shipped in the runtime image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip setuptools wheel \
 && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------- runtime ---
FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app

# curl is required by the container healthcheck below.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --system --gid 10001 nvo \
 && useradd --system --uid 10001 --gid nvo --create-home --shell /usr/sbin/nologin nvo

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=nvo:nvo alembic.ini pyproject.toml ./
COPY --chown=nvo:nvo alembic ./alembic
COPY --chown=nvo:nvo app ./app

USER nvo

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://localhost:8000/health || exit 1

# Workers are process-based; the app's background collectors run in worker 1
# only when replicas are scaled at the orchestrator level instead.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-config", "/dev/null"]
