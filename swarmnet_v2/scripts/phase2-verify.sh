#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

N_DRONES="${N_DRONES:-2}"

docker compose ps
docker compose exec -T px4_sitl python3 /px4_config/scripts/drone_spawn.py --n "$N_DRONES" --dry-run
docker compose exec -T ros2_nodes bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  ros2 topic list | grep -E "^/swarm/(desired_formation|drone_1/state)$"
  ros2 topic echo /swarm/desired_formation --once
'

cat <<'EOF'

Manual acceptance check:
1. QGroundControl displays the expected vehicle IDs on one UDP port, 14550.
2. At N=50, the target layout is 5 rows by 10 columns at 2 m spacing.
3. Run: python3 scripts/profile_resources.py --duration 60
4. Confirm peak RAM is below 14 GiB and no PX4 process has exited.
EOF
