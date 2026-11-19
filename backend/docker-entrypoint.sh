#!/bin/sh
# Apply migrations (retrying while the database starts), then serve the API.
set -e

# Retrying cannot fix a missing value, so stop at once with a clear message.
if [ -n "${DATABASE_URL+set}" ] && [ -z "$(echo "$DATABASE_URL" | tr -d '[:space:]')" ]; then
  echo "DATABASE_URL is empty; set it to a PostgreSQL connection string such as postgresql://user:password@host:5432/dbname" >&2
  exit 1
fi

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  attempt=1
  until alembic upgrade head; do
    if [ "$attempt" -ge 10 ]; then
      echo "Database migrations failed after $attempt attempts" >&2
      exit 1
    fi
    echo "Database not ready (attempt $attempt); retrying in 3s" >&2
    attempt=$((attempt + 1))
    sleep 3
  done
fi

exec uvicorn --factory app.main:create_app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-1}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-*}"
