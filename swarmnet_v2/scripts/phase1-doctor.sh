#!/usr/bin/env bash
set -euo pipefail

failures=0

check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "[PASS] $label"
  else
    echo "[FAIL] $label"
    failures=$((failures + 1))
  fi
}

check "Docker CLI available" docker --version
check "Docker Desktop daemon running" docker info
check "PX4 source checkout exists" test -f PX4-Autopilot/Tools/setup/ubuntu.sh
check "Compose configuration valid" docker compose --env-file .env config --quiet

if [[ "$failures" -ne 0 ]]; then
  echo "Phase 1 prerequisites are not ready. See README.md."
  exit 1
fi

echo "Phase 1 host prerequisites are ready."
