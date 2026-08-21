"""Publish Phase 2 grid formation targets for all swarm followers."""

from __future__ import annotations

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from swarmnet_msgs.msg import DroneTarget, FormationTargets

from swarmnet_master.formation import grid_targets


class MasterNode(Node):
    """Latched publisher for the Phase 2 static grid formation."""

    def __init__(self) -> None:
        super().__init__("swarmnet_master")
        self.declare_parameter("n_drones", 50)
        self.declare_parameter("grid_width", 7)
        self.declare_parameter("spacing_m", 2.0)
        self.declare_parameter("altitude_m", 5.0)
        qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.publisher = self.create_publisher(FormationTargets, "/swarm/formation_targets", qos)
        self.timer = self.create_timer(1.0, self.publish_grid)
        self.publish_grid()

    def publish_grid(self) -> None:
        """Publish all assigned hover positions as one formation message."""
        message = FormationTargets()
        message.formation_type = 0
        message.targets = []
        for target in grid_targets(
            self.get_parameter("n_drones").value,
            self.get_parameter("grid_width").value,
            self.get_parameter("spacing_m").value,
            self.get_parameter("altitude_m").value,
        ):
            target_message = DroneTarget()
            target_message.drone_id = target.drone_id
            target_message.target_x = target.x
            target_message.target_y = target.y
            target_message.target_z = target.z
            target_message.target_yaw = target.yaw
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
