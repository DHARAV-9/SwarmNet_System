"""Launch MAVROS2 bridges with isolated namespaces and UDP ports."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from swarmnet_master.routing import VehicleRoute, validate_fleet_size


def _bridges(context):
    n_drones = int(LaunchConfiguration("n_drones").perform(context))
    validate_fleet_size(n_drones)
    px4_host = LaunchConfiguration("px4_host").perform(context)
    actions = []
    for drone_id in range(1, n_drones + 1):
        route = VehicleRoute(drone_id)
        actions.append(
            Node(
                package="mavros",
                executable="mavros_node",
                namespace=route.namespace,
                name="bridge",
                parameters=[
                    {
                        "fcu_url": route.fcu_url(px4_host),
                        "tgt_system": drone_id,
                        "tgt_component": 1,
                    }
                ],
                output="screen",
            )
        )
    return actions


def generate_launch_description() -> LaunchDescription:
    """Generate a MAVROS bridge for each active PX4 vehicle."""
    return LaunchDescription(
        [
            DeclareLaunchArgument("n_drones", default_value="2"),
            DeclareLaunchArgument("px4_host", default_value="px4_sitl"),
            OpaqueFunction(function=_bridges),
        ]
    )
