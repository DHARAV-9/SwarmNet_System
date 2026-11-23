"""Launch one master plus N static formation-hold follower nodes."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

from swarmnet_master.formation import DEFAULT_ALTITUDE_M, DEFAULT_GRID_WIDTH, DEFAULT_SPACING_M
from swarmnet_master.routing import validate_fleet_size


def _followers(context):
    n_drones = int(LaunchConfiguration("n_drones").perform(context))
    validate_fleet_size(n_drones)
    params_file = LaunchConfiguration("follower_params_file").perform(context)
    return [
        Node(
            package="swarmnet_follower",
            executable="follower_node",
            name=f"follower_{drone_id}",
            parameters=([params_file] if params_file else []) + [{"drone_id": drone_id}],
            output="screen",
        )
        for drone_id in range(1, n_drones + 1)
    ]


def generate_launch_description() -> LaunchDescription:
    """Generate a master and the requested number of formation followers."""
    n_drones = LaunchConfiguration("n_drones")
    return LaunchDescription(
        [
            DeclareLaunchArgument("n_drones", default_value="2"),
            DeclareLaunchArgument("grid_width", default_value=str(DEFAULT_GRID_WIDTH)),
            DeclareLaunchArgument("spacing_m", default_value=str(DEFAULT_SPACING_M)),
            DeclareLaunchArgument("altitude_m", default_value=str(DEFAULT_ALTITUDE_M)),
            DeclareLaunchArgument("follower_params_file", default_value=""),
        Node(
            package="swarmnet_master",
            executable="master_node",
            name="master",
                parameters=[{
                    "n_drones": ParameterValue(n_drones, value_type=int),
                    "grid_width": ParameterValue(LaunchConfiguration("grid_width"), value_type=int),
                    "spacing_m": ParameterValue(LaunchConfiguration("spacing_m"), value_type=float),
                    "altitude_m": ParameterValue(LaunchConfiguration("altitude_m"), value_type=float),
                }],
            output="screen",
        ),
            OpaqueFunction(function=_followers),
        ]
    )
