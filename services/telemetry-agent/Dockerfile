# syntax=docker/dockerfile:1.7
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NVO_API_PATH=/opt/nvo-api

RUN pip install --no-cache-dir psutil==6.1.1 nvidia-ml-py==12.560.30 httpx==0.28.1 structlog==24.4.0 \
 && groupadd --system --gid 10001 nvo \
 && useradd --system --uid 10001 --gid nvo --create-home --shell /usr/sbin/nologin nvo

WORKDIR /app

# The collector implementations are shared with the API package.
COPY --chown=nvo:nvo apps/api/app /opt/nvo-api/app
COPY --chown=nvo:nvo services/telemetry-agent/agent.py ./agent.py

USER nvo

ENTRYPOINT ["python", "agent.py"]
