# syntax=docker/dockerfile:1.7
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NVO_API_PATH=/opt/nvo-api

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir \
      fastapi==0.115.6 "uvicorn[standard]==0.34.0" httpx==0.28.1 \
      pydantic==2.10.4 pydantic-settings==2.7.0 prometheus-client==0.21.1 structlog==24.4.0 \
 && groupadd --system --gid 10001 nvo \
 && useradd --system --uid 10001 --gid nvo --create-home --shell /usr/sbin/nologin nvo

WORKDIR /app
COPY --chown=nvo:nvo apps/api/app /opt/nvo-api/app
COPY --chown=nvo:nvo services/inference-gateway/gateway.py ./gateway.py
USER nvo

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8080/health || exit 1

CMD ["uvicorn", "gateway:app", "--host", "0.0.0.0", "--port", "8080"]
