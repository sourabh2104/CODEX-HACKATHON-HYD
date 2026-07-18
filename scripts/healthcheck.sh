#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root_dir"

if [[ ! -f .env ]]; then
  cp .env.example .env
fi

compose=(docker compose --env-file .env)
"${compose[@]}" ps

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" .env | tail -n 1
}

backend_port="$(env_value BACKEND_PORT)"
frontend_port="$(env_value FRONTEND_PORT)"
backend_health_path="$(env_value BACKEND_HEALTH_PATH)"
backend_url="http://localhost:${backend_port:-8000}"
frontend_url="http://localhost:${frontend_port:-5173}"

check_url() {
  local label="$1"
  shift
  local url
  for url in "$@"; do
    if curl --fail --silent --show-error --max-time 5 "$url" >/dev/null; then
      echo "OK  $label ($url)"
      return 0
    fi
  done
  echo "FAIL $label" >&2
  return 1
}

check_url frontend "$frontend_url"
check_url backend "$backend_url${backend_health_path:-/healthz}" "$backend_url/livez" "$backend_url/health"
