#!/bin/sh
set -eu

if [ -n "${FRONTEND_COMMAND:-}" ]; then
  exec sh -c "$FRONTEND_COMMAND"
fi

if [ ! -f /workspace/frontend/package.json ]; then
  echo 'frontend/package.json is not present; add the frontend app before starting Compose.' >&2
  exit 1
fi

cd /workspace/frontend
port="${FRONTEND_PORT:-5173}"
script="${FRONTEND_SCRIPT:-dev}"

if [ -f pnpm-lock.yaml ]; then
  exec corepack pnpm run "$script" --host 0.0.0.0 --port "$port"
elif [ -f yarn.lock ]; then
  exec corepack yarn run "$script" --host 0.0.0.0 --port "$port"
else
  exec npm run "$script" -- --host 0.0.0.0 --port "$port"
fi
