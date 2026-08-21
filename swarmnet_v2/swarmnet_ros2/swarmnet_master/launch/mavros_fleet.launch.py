"""Launch MAVROS2 bridges with isolated namespaces and UDP ports."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _bridges(context):
    n_drones = int(LaunchConfiguration("n_drones").perform(context))
    base_remote_port = int(LaunchConfiguration("base_remote_port").perform(context))
    actions = []
    for drone_id in range(1, n_drones + 1):
        remote_port = base_remote_port + drone_id - 1
        local_port = 14600 + drone_id - 1
        actions.append(
            Node(
                package="mavros",
                executable="mavros_node",
                namespace=f"drone_{drone_id}/mavros",
                name="bridge",
                parameters=[
                    {
                        "fcu_url": f"udp://:{local_port}@swarmnet_px4:{remote_port}",
                        "target_system_id": drone_id,
                        "target_component_id": 1,
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
            DeclareLaunchArgument("n_drones", default_value="50"),
            DeclareLaunchArgument("base_remote_port", default_value="14550"),
            OpaqueFunction(function=_bridges),
        ]
    )
