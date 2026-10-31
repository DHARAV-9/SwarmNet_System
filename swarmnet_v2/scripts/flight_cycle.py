"""Exercise one simulated PX4 vehicle using measured XRCE-DDS telemetry."""

from __future__ import annotations

import argparse
import json
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from px4_msgs.msg import (
    OffboardControlMode,
    TrajectorySetpoint,
    VehicleCommand,
    VehicleLandDetected,
    VehicleLocalPosition,
    VehicleStatus,
)


class FlightCycle(Node):
    """Stream setpoints and observe arm, hover, landing and disarm states."""

    def __init__(self, altitude: float, hover_seconds: float) -> None:
        super().__init__("swarmnet_flight_cycle")
        self.altitude = altitude
        self.hover_seconds = hover_seconds
        self.status = None
        self.position = None
        self.landed = None
        self.last_state = 0.0
        self.last_position = 0.0
        self.stage = "waiting"
        self.stage_started = time.monotonic()
        self.started = self.stage_started
        self.last_command = 0.0
        self.complete = False
        prefix = "/drone_1/fmu"
        self.mode_publisher = self.create_publisher(OffboardControlMode, f"{prefix}/in/offboard_control_mode", 10)
        self.target_publisher = self.create_publisher(TrajectorySetpoint, f"{prefix}/in/trajectory_setpoint", 10)
        self.command_publisher = self.create_publisher(VehicleCommand, f"{prefix}/in/vehicle_command", 10)
        self.create_subscription(VehicleStatus, f"{prefix}/out/vehicle_status", self.on_status, qos_profile_sensor_data)
        self.create_subscription(VehicleLocalPosition, f"{prefix}/out/vehicle_local_position", self.on_position, qos_profile_sensor_data)
        self.create_subscription(VehicleLandDetected, f"{prefix}/out/vehicle_land_detected", self.on_landed, qos_profile_sensor_data)
        self.create_timer(0.05, self.tick)

    def on_status(self, message) -> None:
        """Store measured PX4 arming/navigation status."""
        self.status = message
        self.last_state = time.monotonic()

    def on_position(self, message) -> None:
        """Store measured local NED position."""
        self.position = message
        self.last_position = time.monotonic()

    def on_landed(self, message) -> None:
        """Store the measured landing-detector result."""
        self.landed = message

    def transition(self, stage: str) -> None:
        """Record only transitions established by the telemetry checks."""
        self.stage = stage
        self.stage_started = time.monotonic()
        print(json.dumps({"event": stage, "elapsed_s": self.stage_started - self.started,
                          "measured_z_ned": self.position.z if self.position else None}), flush=True)

    def command(self, command: int, param1: float = 0.0, param2: float = 0.0) -> None:
        """Send a command addressed explicitly to simulated system 1."""
        message = VehicleCommand()
        message.timestamp = self.get_clock().now().nanoseconds // 1000
        message.command = command
        message.param1 = param1
        message.param2 = param2
        message.target_system = 1
        message.target_component = 1
        message.source_system = 255
        message.source_component = 190
        message.from_external = True
        self.command_publisher.publish(message)

    def tick(self) -> None:
        """Advance only when fresh aircraft telemetry satisfies the stage."""
        now = time.monotonic()
        if now - self.started > 180:
            raise RuntimeError(f"flight cycle timeout in {self.stage}")
        fresh = self.status is not None and self.position is not None and now - self.last_state < 2 and now - self.last_position < 2
        if not fresh:
            if self.stage != "waiting":
                raise RuntimeError("measured PX4 telemetry became stale")
            return
        if self.stage in {"waiting", "prestream", "arming", "takeoff", "hover"}:
            mode = OffboardControlMode()
            mode.timestamp = self.get_clock().now().nanoseconds // 1000
            mode.position = True
            self.mode_publisher.publish(mode)
            target = TrajectorySetpoint()
            target.timestamp = mode.timestamp
            target.position = [0.0, 0.0, -self.altitude]
            target.yaw = 0.0
            self.target_publisher.publish(target)
        if self.stage == "waiting" and self.position.xy_valid and self.position.z_valid:
            self.transition("prestream")
        elif self.stage == "prestream" and now - self.stage_started > 2:
            self.transition("arming")
        elif self.stage == "arming":
            if now - self.last_command > 1:
                self.command(VehicleCommand.VEHICLE_CMD_DO_SET_MODE, 1.0, 6.0)
                self.command(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 1.0)
                self.last_command = now
            if self.status.arming_state == VehicleStatus.ARMING_STATE_ARMED:
                self.transition("takeoff")
        elif self.stage == "takeoff" and abs(self.position.z + self.altitude) < 0.4:
            self.transition("hover")
        elif self.stage == "hover":
            if abs(self.position.z + self.altitude) > 0.5:
                raise RuntimeError("measured altitude left hover tolerance")
            if now - self.stage_started >= self.hover_seconds:
                self.command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
                self.transition("landing")
        elif self.stage == "landing" and self.landed is not None and self.landed.landed:
            self.command(VehicleCommand.VEHICLE_CMD_COMPONENT_ARM_DISARM, 0.0)
            self.transition("disarming")
        elif self.stage == "disarming" and self.status.arming_state == VehicleStatus.ARMING_STATE_DISARMED:
            self.transition("disarmed")
            self.complete = True


def main() -> None:
    """Run the simulation-only lifecycle check and fail on missing evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--altitude", type=float, default=3.0)
    parser.add_argument("--hover-seconds", type=float, default=10.0)
    args = parser.parse_args()
    if args.altitude <= 0 or args.hover_seconds <= 0:
        parser.error("altitude and hover duration must be positive")
    rclpy.init()
    node = FlightCycle(args.altitude, args.hover_seconds)
    try:
        while rclpy.ok() and not node.complete:
            rclpy.spin_once(node, timeout_sec=0.1)
    except Exception:
        node.command(VehicleCommand.VEHICLE_CMD_NAV_LAND)
        raise
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
