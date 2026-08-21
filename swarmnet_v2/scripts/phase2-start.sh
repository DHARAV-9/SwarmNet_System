#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi

N_DRONES="${N_DRONES:-50}"

docker compose up -d --build
docker compose exec -T ros2_nodes bash -lc '
  source /opt/ros/humble/setup.bash
  cd /ros2_ws
  colcon build --packages-select swarmnet_msgs swarmnet_master swarmnet_follower
'
docker compose exec -d ros2_nodes bash -lc "
  source /opt/ros/humble/setup.bash &&
  source /ros2_ws/install/setup.bash &&
  ros2 launch swarmnet_master swarm_grid.launch.py n_drones:=${N_DRONES}
"
docker compose exec -d ros2_nodes bash -lc "
  source /opt/ros/humble/setup.bash &&
  source /ros2_ws/install/setup.bash &&
  ros2 launch swarmnet_master mavros_fleet.launch.py n_drones:=${N_DRONES}
"
docker compose exec px4_sitl python3 /px4_config/scripts/drone_spawn.py --n "$N_DRONES"
