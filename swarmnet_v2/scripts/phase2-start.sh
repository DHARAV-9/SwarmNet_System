#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
N_DRONES="${N_DRONES:-2}"

docker compose up -d --no-build --wait
docker compose exec -T ros2_nodes bash -lc '
  set -e
  source /opt/ros/humble/setup.bash
  cd /ros2_ws
  colcon build --base-paths src/swarmnet --packages-select swarmnet_msgs swarmnet_master swarmnet_follower
'
docker compose exec -d ros2_nodes bash -lc '
  source /opt/ros/humble/setup.bash &&
  source /ros2_ws/install/setup.bash &&
  exec ros2 launch swarmnet_master mavros_fleet.launch.py n_drones:="$1"
' _ "$N_DRONES"
docker compose exec -d ros2_nodes bash -lc '
  source /opt/ros/humble/setup.bash &&
  source /ros2_ws/install/setup.bash &&
  exec ros2 launch swarmnet_master swarm_grid.launch.py n_drones:="$1" follower_params_file:="$2"
' _ "$N_DRONES" "${FOLLOWER_PARAMS_FILE:-}"
docker compose exec px4_sitl python3 /px4_config/scripts/drone_spawn.py --n "$N_DRONES"
