"""Launch one master plus N static formation-hold follower nodes."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def _followers(context):
    n_drones = int(LaunchConfiguration("n_drones").perform(context))
    return [
        Node(
            package="swarmnet_follower",
            executable="follower_node",
            name=f"follower_{drone_id}",
            parameters=[{"drone_id": drone_id}],
            output="screen",
        )
        for drone_id in range(1, n_drones + 1)
    ]


def generate_launch_description() -> LaunchDescription:
    """Generate a master and the requested number of formation followers."""
    n_drones = LaunchConfiguration("n_drones")
    return LaunchDescription(
        [
            DeclareLaunchArgument("n_drones", default_value="50"),
        Node(
            package="swarmnet_master",
            executable="master_node",
            name="master",
            parameters=[{"n_drones": n_drones}],
            output="screen",
        ),
            OpaqueFunction(function=_followers),
        ]
    )
