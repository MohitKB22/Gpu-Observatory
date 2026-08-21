# syntax=docker/dockerfile:1.7
FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN groupadd --system --gid 10001 nvo \
 && useradd --system --uid 10001 --gid nvo --create-home --shell /usr/sbin/nologin nvo

WORKDIR /app
COPY --chown=nvo:nvo services/workload-generator/generate.py ./generate.py
USER nvo

ENTRYPOINT ["python", "generate.py"]
