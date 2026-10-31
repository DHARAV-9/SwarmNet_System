"""Phase 2 follower: relay its assigned grid target to MAVROS2."""

from __future__ import annotations

import time

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from swarmnet_msgs.msg import DroneState, FormationTargets
from swarmnet_follower.topics import state_topic


class FollowerNode(Node):
    """Hold one drone at its target using a continuous MAVROS position stream."""

    def __init__(self) -> None:
        super().__init__("swarmnet_follower")
        self.declare_parameter("drone_id", 1)
        self.declare_parameter("hold_rate_hz", 20.0)
        self.drone_id = int(self.get_parameter("drone_id").value)
        self.target: tuple[float, float, float, float] | None = None
        formation_qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.create_subscription(
            FormationTargets,
            "/swarm/formation_targets",
            self.on_formation_targets,
            formation_qos,
        )
        namespace = f"/drone_{self.drone_id}/mavros"
        self.setpoint_publisher = self.create_publisher(
            PoseStamped,
            f"{namespace}/setpoint_position/local",
            10,
        )
        self.state_publisher = self.create_publisher(
            DroneState,
            state_topic(self.drone_id),
            10,
        )
        hold_rate = float(self.get_parameter("hold_rate_hz").value)
        self.create_timer(1.0 / hold_rate, self.publish_hold_setpoint)
        self.create_timer(0.1, self.publish_state)

    def on_formation_targets(self, message: FormationTargets) -> None:
        """Store this follower's assigned static grid target."""
        for target in message.targets:
            if target.drone_id == self.drone_id:
                self.target = (
                    target.target_x,
                    target.target_y,
                    target.target_z,
                    target.target_yaw,
                )
                return

    def publish_hold_setpoint(self) -> None:
        """Stream a local position target at 20 Hz for PX4 OFFBOARD readiness."""
        if self.target is None:
            return
        x, y, z, _ = self.target
        message = PoseStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = "map"
        message.pose.position.x = x
        message.pose.position.y = y
        message.pose.position.z = z
        message.pose.orientation.w = 1.0
        self.setpoint_publisher.publish(message)

    def publish_state(self) -> None:
        """Publish Phase 2 formation target telemetry until EKF is introduced."""
        if self.target is None:
            return
        x, y, z, _ = self.target
        message = DroneState()
        message.drone_id = self.drone_id
        message.x = x
        message.y = y
        message.z = z
        message.battery = 100.0
        message.alive = True
        message.timestamp = time.time()
        self.state_publisher.publish(message)


def main() -> None:
    """Start one follower node."""
    rclpy.init()
    node = FollowerNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
