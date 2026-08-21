#!/usr/bin/env bash
# Build the distributable ZIP, excluding dependencies and build output.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="nvidia-ai-performance-observatory"
ZIP="${ROOT}/${NAME}-production.zip"

cd "$ROOT"
rm -f "$ZIP"

echo "packaging ${NAME}…"
zip -r -q "$ZIP" . \
  -x '*/node_modules/*' \
  -x '*/.venv/*' \
  -x '*/__pycache__/*' \
  -x '*.pyc' \
  -x '*/.pytest_cache/*' \
  -x '*/.mypy_cache/*' \
  -x '*/.ruff_cache/*' \
  -x '*/.next/*' \
  -x '*/out/*' \
  -x '*/dist/*' \
  -x '*/build/*' \
  -x '*/coverage/*' \
  -x '*/htmlcov/*' \
  -x '.coverage' \
  -x 'coverage.xml' \
  -x '*.db' -x '*.sqlite' -x '*.sqlite3' \
  -x '.env' -x '.env.*' \
  -x '*/.git/*' -x '.git/*' \
  -x '*/.idea/*' -x '*/.vscode/*' \
  -x '.DS_Store' -x '*/.DS_Store' \
  -x '*.tsbuildinfo' \
  -x 'next-env.d.ts' \
  -x "${NAME}-production.zip"

echo "wrote $ZIP ($(du -h "$ZIP" | cut -f1))"
