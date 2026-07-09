#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PRUNE_HEAVY=false
if [[ "${1:-}" == "--prune-heavy" ]]; then
  PRUNE_HEAVY=true
fi

echo "Removing local caches and generated build artifacts..."
rm -rf \
  backend/__pycache__ \
  frontend/.angular \
  frontend/dist \
  .pytest_cache

find . -name ".DS_Store" -delete
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
find . -name "*.pyc" -delete

echo
echo "Heavy local directories:"
for path in backend/venv frontend/node_modules backend/models backend/runtime; do
  if [[ -e "$path" ]]; then
    du -sh "$path" 2>/dev/null || true
  fi
done

if [[ "$PRUNE_HEAVY" == "true" ]]; then
  echo
  echo "Pruning heavy local directories..."
  rm -rf backend/venv frontend/node_modules backend/models backend/runtime
fi

cat <<'MSG'
Done.

Heavy directories are not removed by default:
- backend/venv
- frontend/node_modules
- backend/models
- backend/runtime

Run `bash scripts/clean_workspace.sh --prune-heavy` only when you want a clean reinstall and are okay removing the local virtualenv, node_modules, model files, and persisted sessions.
MSG
