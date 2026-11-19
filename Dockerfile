# Single-container image: builds the dashboard and serves it from the FastAPI backend, so the whole
# app runs as one web service with one URL (used by render.yaml). docker-compose.yml still runs the
# frontend in its own nginx container.

FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STATIC_DIR=/app/static

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 10001 observatory
COPY --chown=observatory:observatory backend/alembic.ini backend/docker-entrypoint.sh ./
COPY --chown=observatory:observatory backend/alembic ./alembic
COPY --chown=observatory:observatory backend/app ./app
COPY --chown=observatory:observatory --from=frontend /frontend/dist ./static
RUN chmod +x docker-entrypoint.sh

USER observatory
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=4)" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
