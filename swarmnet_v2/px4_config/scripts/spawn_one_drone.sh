#!/usr/bin/env bash
set -euo pipefail

PX4_DIR="${PX4_DIR:-/opt/PX4-Autopilot}"
PX4_INSTANCE="${PX4_INSTANCE:-0}"
SWARM_STATE_DIR="${SWARM_STATE_DIR:-/var/log/swarmnet/px4/instance_${PX4_INSTANCE}}"

if [[ ! -d "$PX4_DIR" ]]; then
  echo "PX4 source not found at $PX4_DIR. Clone PX4-Autopilot on the host first."
  exit 1
fi

mkdir -p "$SWARM_STATE_DIR"
cd "$SWARM_STATE_DIR"

if [[ ! -x "$PX4_DIR/build/px4_sitl_default/bin/px4" ]]; then
  echo "Invalid PX4 source directory: $PX4_DIR"
  exit 1
fi

export GZ_SIM_RESOURCE_PATH="${GZ_SIM_RESOURCE_PATH:-}"
export GZ_SIM_SYSTEM_PLUGIN_PATH="${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
source "$PX4_DIR/build/px4_sitl_default/rootfs/gz_env.sh"
export HEADLESS=1
export PX4_SYS_AUTOSTART=4001
export PX4_SIM_MODEL=gz_x500
export PX4_GZ_WORLD=default
export PX4_GZ_MODEL_POSE="${PX4_GZ_MODEL_POSE:-0,0,0.15,0,0,0}"
unset PX4_GZ_MODEL_NAME PX4_GZ_STANDALONE
if [[ "$PX4_INSTANCE" -gt 0 ]]; then
  export PX4_GZ_STANDALONE=1
fi
export SWARM_QGC_IP="$(getent ahostsv4 host.docker.internal | awk 'NR==1 {print $1}')"
export SWARM_ROS_IP="$(getent ahostsv4 ros2_nodes | awk 'NR==1 {print $1}')"
test -n "$SWARM_QGC_IP"
test -n "$SWARM_ROS_IP"
exec "$PX4_DIR/build/px4_sitl_default/bin/px4" \
  "$PX4_DIR/build/px4_sitl_default/rootfs" \
  -i "$PX4_INSTANCE" -w "$SWARM_STATE_DIR" -s /px4_config/scripts/swarm_startup.sh -d
