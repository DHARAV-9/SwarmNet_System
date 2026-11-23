"""Relay desired positions to MAVROS2 and publish measured vehicle state."""

from __future__ import annotations

import time
from math import cos, isfinite, isnan, sin

import rclpy
from geometry_msgs.msg import PoseStamped, TwistStamped
from mavros_msgs.msg import State
from rcl_interfaces.msg import ParameterDescriptor
from rclpy.clock import Clock, ClockType
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
from sensor_msgs.msg import BatteryState
from swarmnet_msgs.msg import DesiredFormation, DroneState

from swarmnet_follower.frames import LocalFrame
from swarmnet_follower.telemetry import Telemetry
from swarmnet_follower.topics import state_topic


class FollowerNode(Node):
    """Hold one drone at its target using a continuous MAVROS position stream."""

    def __init__(self) -> None:
        super().__init__("swarmnet_follower")
        self.declare_parameter("drone_id", 1)
        self.declare_parameter("hold_rate_hz", 20.0)
        fixed = ParameterDescriptor(read_only=True)
        self.declare_parameter("telemetry_timeout_s", 2.0, fixed)
        self.declare_parameter("battery_timeout_s", 5.0, fixed)
        self.declare_parameter("mavros_local_frame_id", "map", fixed)
        self.declare_parameter("local_origin_world_enu", [float("nan")] * 3, fixed)
        self.drone_id = int(self.get_parameter("drone_id").value)
        self.local_frame_id = self.get_parameter("mavros_local_frame_id").value
        origin = tuple(self.get_parameter("local_origin_world_enu").value)
        self.frame = None if len(origin) == 3 and all(map(isnan, origin)) else LocalFrame(origin)
        if self.frame is None:
            self.get_logger().warning("Configure local_origin_world_enu; world position and setpoints are disabled.")
        self.telemetry = Telemetry(
            self.get_parameter("telemetry_timeout_s").value, self.get_parameter("battery_timeout_s").value
        )
        self.desired: tuple[float, float, float, float] | None = None
        formation_qos = QoSProfile(
            depth=1,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )
        self.create_subscription(
            DesiredFormation,
            "/swarm/desired_formation",
            self.on_desired_formation,
            formation_qos,
        )
        namespace = f"/drone_{self.drone_id}/mavros/bridge"
        self.create_subscription(PoseStamped, f"{namespace}/local_position/pose",
                                 self.on_pose, qos_profile_sensor_data)
        self.create_subscription(TwistStamped, f"{namespace}/local_position/velocity_local",
                                 self.on_velocity, qos_profile_sensor_data)
        self.create_subscription(BatteryState, f"{namespace}/battery", self.on_battery, qos_profile_sensor_data)
        self.create_subscription(State, f"{namespace}/state", self.on_connection, qos_profile_sensor_data)
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
        self.create_timer(0.1, self.publish_state, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def on_desired_formation(self, message: DesiredFormation) -> None:
        """Store this follower's desired world ENU pose, not its measured state."""
        self.desired = None
        for target in message.targets:
            if target.drone_id == self.drone_id:
                desired = target.x, target.y, target.z, target.yaw
                if all(map(isfinite, desired)):
                    self.desired = desired
                return

    def on_pose(self, message: PoseStamped) -> None:
        position = message.pose.position
        self.telemetry.position = (
            ((position.x, position.y, position.z), time.monotonic())
            if message.header.frame_id == self.local_frame_id else None
        )

    def on_velocity(self, message: TwistStamped) -> None:
        velocity = message.twist.linear
        self.telemetry.velocity = (
            ((velocity.x, velocity.y, velocity.z), time.monotonic())
            if message.header.frame_id == self.local_frame_id else None
        )

    def on_battery(self, message: BatteryState) -> None:
        self.telemetry.battery = message.percentage, time.monotonic()

    def on_connection(self, message: State) -> None:
        self.telemetry.update_connection(message.connected, time.monotonic())

    def publish_hold_setpoint(self) -> None:
        """Stream a local position target at 20 Hz for PX4 OFFBOARD readiness."""
        if self.desired is None or self.frame is None or not self.telemetry.connected(time.monotonic()):
            return
        x, y, z, yaw = self.desired
        message = PoseStamped()
        message.header.stamp = self.get_clock().now().to_msg()
        message.header.frame_id = self.local_frame_id
        message.pose.position.x, message.pose.position.y, message.pose.position.z = self.frame.world_to_local((x, y, z))
        message.pose.orientation.z = sin(yaw / 2)
        message.pose.orientation.w = cos(yaw / 2)
        self.setpoint_publisher.publish(message)

    def publish_state(self) -> None:
        """Publish measured state, including an unhealthy state on data loss."""
        reading = self.telemetry.snapshot(time.monotonic(), self.frame)
        message = DroneState()
        message.drone_id = self.drone_id
        message.x, message.y, message.z = reading.position
        message.vx, message.vy, message.vz = reading.velocity
        message.battery = reading.battery_percent
        message.alive = reading.alive
        message.comms_healthy = reading.comms_healthy
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
