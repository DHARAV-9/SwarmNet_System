#!/usr/bin/env bash
set -euo pipefail

PX4_DIR="${PX4_DIR:-/workspace/PX4-Autopilot}"
HEADLESS="${HEADLESS:-0}"

if [[ ! -d "$PX4_DIR" ]]; then
  echo "PX4 source not found at $PX4_DIR. Clone PX4-Autopilot on the host first."
  exit 1
fi

cd "$PX4_DIR"

if [[ ! -f Tools/setup/ubuntu.sh ]]; then
  echo "Invalid PX4 source directory: $PX4_DIR"
  exit 1
fi

if [[ "$HEADLESS" == "1" ]]; then
  export HEADLESS=1
  make px4_sitl gz_x500
else
  : "${DISPLAY:?DISPLAY must be set for Gazebo GUI forwarding}"
  make px4_sitl gz_x500
fi
