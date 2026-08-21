#!/usr/bin/env bash
set -euo pipefail

docker compose ps
docker compose exec -T px4_sitl bash -lc 'pgrep -af "px4|gz"'
nc -zvu 127.0.0.1 14550

cat <<'EOF'

Manual acceptance check:
1. Open QGroundControl on macOS.
2. Verify one vehicle connects on UDP port 14550.
3. Arm, then disarm, the vehicle from QGroundControl.
4. Confirm the XQuartz Gazebo window shows the X500 model when HEADLESS=0.
EOF
