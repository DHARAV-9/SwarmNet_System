#!/bin/sh
. "${R}etc/init.d-posix/rcS"
set -e

vehicle_id=$((px4_instance + 1))
offboard_local=${SWARM_OFFBOARD_PORT:-$((15000 + px4_instance))}
offboard_remote=${SWARM_MAVROS_PORT:-$((16000 + px4_instance))}
gcs_local=${SWARM_GCS_SOURCE_PORT:-$((18570 + px4_instance))}

param set MAV_SYS_ID "$vehicle_id"
param set COM_RCL_EXCEPT 4
param set COM_RC_IN_MODE 4
param show MAV_SYS_ID

mavlink stop-all
mavlink start -u "$gcs_local" -o "${QGC_PORT:-14550}" -t "$SWARM_QGC_IP" -r 4000000
mavlink start -u "$offboard_local" -o "$offboard_remote" -t "$SWARM_ROS_IP" -r 4000000 -m onboard
mavlink stream -u "$gcs_local" -s LOCAL_POSITION_NED -r 20
mavlink stream -u "$gcs_local" -s GLOBAL_POSITION_INT -r 10
mavlink stream -u "$offboard_local" -s LOCAL_POSITION_NED -r 20
uxrce_dds_client stop
uxrce_dds_client start -t udp -h "$SWARM_ROS_IP" -p 8888 -n "drone_$vehicle_id"
mavlink boot_complete
mavlink status
uxrce_dds_client status
echo "SwarmNet PX4 instance $px4_instance ready"
