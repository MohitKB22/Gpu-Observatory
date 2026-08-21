#!/usr/bin/env bash
# Verify every component of a running stack.
set -uo pipefail

API="${API_URL:-http://localhost:8000}"
WEB="${WEB_URL:-http://localhost:3000}"
PROM="${PROMETHEUS_URL:-http://localhost:9090}"
GRAFANA="${GRAFANA_URL:-http://localhost:3001}"

pass=0
fail=0

check() {
  local name="$1" url="$2" expect="${3:-200}"
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$url" 2>/dev/null)
  if [ "$code" = "$expect" ]; then
    printf '  \033[32mok\033[0m    %-22s %s\n' "$name" "$url"
    pass=$((pass + 1))
  else
    printf '  \033[31mFAIL\033[0m  %-22s %s (got %s, expected %s)\n' "$name" "$url" "$code" "$expect"
    fail=$((fail + 1))
  fi
}

echo "NVIDIA AI Performance Observatory — health check"
echo
check "api health"      "$API/health"
check "api readiness"   "$API/ready"
check "api metrics"     "$API/metrics"
check "api docs"        "$API/docs"
check "openapi schema"  "$API/openapi.json"
check "frontend"        "$WEB/"
check "prometheus"      "$PROM/-/healthy"
check "grafana"         "$GRAFANA/api/health"

echo
if [ "$fail" -eq 0 ]; then
  echo "all $pass checks passed"
  exit 0
fi
echo "$fail of $((pass + fail)) checks failed"
exit 1
