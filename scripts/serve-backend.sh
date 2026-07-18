#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${BACKEND_COMMAND:-}" ]]; then
  exec bash -lc "$BACKEND_COMMAND"
fi

if [[ ! -d /workspace/backend ]]; then
  echo 'backend/ is not present; add the backend service before starting Compose.' >&2
  exit 1
fi

port="${PORT:-8000}"
module="${BACKEND_MODULE:-}"

if [[ -z "$module" ]]; then
  if [[ -f /workspace/backend/app/main.py ]]; then
    module='app.main:app'
  elif [[ -f /workspace/backend/main.py ]]; then
    module='main:app'
  else
    echo 'Could not find backend/app/main.py or backend/main.py.' >&2
    echo 'Set BACKEND_MODULE (for example, app.main:app) in the environment.' >&2
    exit 1
  fi
fi

exec uvicorn "$module" --host "${HOST:-0.0.0.0}" --port "$port"
