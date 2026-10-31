#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
attempt="${1:-1}"
case "$attempt" in 1|2) ;; *) exit 2 ;; esac
docker compose up -d --no-build --wait
docker compose exec -d ros2_nodes python3 /swarmnet/scripts/capture_evidence.py \
  "/evidence/step3_attempt${attempt}_agent_runtime.txt" -- MicroXRCEAgent udp4 -p 8888 -v 4
docker compose exec -d px4_sitl python3 /swarmnet/scripts/capture_evidence.py \
  "/evidence/step3_attempt${attempt}_vehicle_runtime.txt" -- bash /px4_config/scripts/spawn_one_drone.sh
