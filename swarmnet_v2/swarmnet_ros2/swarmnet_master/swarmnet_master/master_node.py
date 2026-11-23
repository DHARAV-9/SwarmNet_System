"""Publish Phase 2 grid formation targets for all swarm followers."""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from swarmnet_msgs.msg import DesiredDronePose, DesiredFormation

from swarmnet_master.formation import DEFAULT_ALTITUDE_M, DEFAULT_GRID_WIDTH, DEFAULT_SPACING_M, grid_targets


class MasterNode(Node):
    """Latched publisher for the Phase 2 static grid formation."""

    def __init__(self) -> None:
        super().__init__("swarmnet_master")
        self.declare_parameter("n_drones", 2)
        self.declare_parameter("grid_width", DEFAULT_GRID_WIDTH)
        self.declare_parameter("spacing_m", DEFAULT_SPACING_M)
        self.declare_parameter("altitude_m", DEFAULT_ALTITUDE_M)
        qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.publisher = self.create_publisher(DesiredFormation, "/swarm/desired_formation", qos)
        self.timer = self.create_timer(1.0, self.publish_grid)
        self.publish_grid()

    def publish_grid(self) -> None:
        """Publish all assigned hover positions as one formation message."""
        message = DesiredFormation()
        message.formation_type = 0
        message.targets = []
        for target in grid_targets(
            self.get_parameter("n_drones").value,
            self.get_parameter("grid_width").value,
            self.get_parameter("spacing_m").value,
            self.get_parameter("altitude_m").value,
        ):
            target_message = DesiredDronePose()
            target_message.drone_id = target.drone_id
            target_message.x = target.x
            target_message.y = target.y
            target_message.z = target.z
            target_message.yaw = target.yaw
            message.targets.append(target_message)
        self.publisher.publish(message)


def main() -> None:
    """Start the master formation publisher."""
    rclpy.init()
    node = MasterNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
