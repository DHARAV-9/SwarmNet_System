#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

N_DRONES="${N_DRONES:-50}"

docker compose ps
docker compose exec -T px4_sitl python3 /px4_config/scripts/drone_spawn.py --n "$N_DRONES" --dry-run
docker compose exec -T ros2_nodes bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  ros2 topic list | grep -E "^/swarm/(formation_targets|drone_1/state)$"
  ros2 topic echo /swarm/formation_targets --once
'

cat <<'EOF'

Manual acceptance check:
1. QGroundControl displays 50 vehicles on UDP ports 14550-14599.
2. Vehicle icons stay in the 7x7 grid at 2m spacing and 5m altitude.
3. Run: python3 scripts/profile_resources.py --duration 60
4. Confirm peak RAM is below 14 GiB and no PX4 process has exited.
EOF
