FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# All dependencies ship as wheels (psycopg[binary] bundles libpq), so no system packages are needed.
COPY requirements.txt .
RUN pip install -r requirements.txt

RUN useradd --create-home --uid 10001 observatory
COPY --chown=observatory:observatory alembic.ini docker-entrypoint.sh ./
COPY --chown=observatory:observatory alembic ./alembic
COPY --chown=observatory:observatory app ./app
RUN chmod +x docker-entrypoint.sh

USER observatory
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
