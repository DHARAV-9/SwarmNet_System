"""Verify independent holds in the local two-vehicle PX4 SITL fleet."""

import argparse
from dataclasses import dataclass, field
from functools import partial
from math import dist, isfinite
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from mavros_msgs.msg import State
from mavros_msgs.srv import CommandBool, SetMode
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

TOLERANCE_M = 0.35
HOLD_S = 8.0


@dataclass
class Vehicle:
    drone_id: int
    position: tuple[float, float, float] | None = None
    desired: tuple[float, float, float] | None = None
    state: State | None = None
    pose_received_at: float = 0.0
    state_received_at: float = 0.0
    maximum_hold_error_m: dict[str, float] = field(default_factory=dict)

    def ready(self, now: float) -> bool:
        return (self.position is not None and self.state is not None and self.state.connected
                and now - self.pose_received_at < 2.0 and now - self.state_received_at < 2.0)

    def error(self) -> float:
        return dist(self.position, self.desired)


class IndependentHold(Node):
    def __init__(self) -> None:
        super().__init__("swarmnet_step5_hold_check")
        self.vehicles = {drone_id: Vehicle(drone_id) for drone_id in (1, 2)}
        self.setpoint_publishers = {}
        self.mode_clients = {}
        self.arm_clients = {}
        for drone_id, vehicle in self.vehicles.items():
            prefix = f"/drone_{drone_id}/mavros/bridge"
            self.create_subscription(PoseStamped, f"{prefix}/local_position/pose",
                                     partial(self.on_pose, vehicle), qos_profile_sensor_data)
            self.create_subscription(State, f"{prefix}/state",
                                     partial(self.on_state, vehicle), qos_profile_sensor_data)
            self.setpoint_publishers[drone_id] = self.create_publisher(PoseStamped, f"{prefix}/setpoint_position/local", 10)
            self.mode_clients[drone_id] = self.create_client(SetMode, f"{prefix}/set_mode")
            self.arm_clients[drone_id] = self.create_client(CommandBool, f"{prefix}/cmd/arming")
        self.create_timer(0.05, self.publish_desired)

    def on_pose(self, vehicle: Vehicle, message: PoseStamped) -> None:
        point = message.pose.position
        position = point.x, point.y, point.z
        if message.header.frame_id == "map" and all(map(isfinite, position)):
            vehicle.position = position
            vehicle.pose_received_at = time.monotonic()

    def on_state(self, vehicle: Vehicle, message: State) -> None:
        vehicle.state = message
        vehicle.state_received_at = time.monotonic()

    def publish_desired(self) -> None:
        for drone_id, vehicle in self.vehicles.items():
            if vehicle.desired is None:
                continue
            message = PoseStamped()
            message.header.frame_id = "map"
            message.header.stamp = self.get_clock().now().to_msg()
            message.pose.position.x, message.pose.position.y, message.pose.position.z = vehicle.desired
            message.pose.orientation.w = 1.0
            self.setpoint_publishers[drone_id].publish(message)

    def wait_for(self, label, predicate, timeout) -> None:
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() >= deadline:
                self.report(label)
                raise RuntimeError(f"Timeout: {label}")
            rclpy.spin_once(self, timeout_sec=0.05)

    def report(self, label: str) -> None:
        for vehicle in self.vehicles.values():
            state = vehicle.state
            print(f"vehicle={vehicle.drone_id} stage={label!r} "
                  f"desired_local_enu={vehicle.desired} measured_local_enu={vehicle.position} "
                  f"connected={bool(state and state.connected)} armed={bool(state and state.armed)} "
                  f"mode={state.mode if state else 'unknown'}", flush=True)

    def mode(self, mode: str) -> None:
        requests = [client.call_async(SetMode.Request(custom_mode=mode)) for client in self.mode_clients.values()]
        self.wait_for(f"{mode} response", lambda: all(request.done() for request in requests), 8)
        for drone_id, request in zip(self.vehicles, requests):
            print(f"vehicle={drone_id} mode_request={mode} response={request.result()}", flush=True)
            if not request.result().mode_sent:
                raise RuntimeError(f"Vehicle {drone_id} rejected {mode} request")

    def arm(self) -> None:
        requests = [client.call_async(CommandBool.Request(value=True)) for client in self.arm_clients.values()]
        self.wait_for("arming response", lambda: all(request.done() for request in requests), 12)
        for drone_id, request in zip(self.vehicles, requests):
            print(f"vehicle={drone_id} arm_response={request.result()}", flush=True)
            if not request.result().success:
                raise RuntimeError(f"Vehicle {drone_id} rejected arm: {request.result().result}")

    def in_offboard(self) -> bool:
        now = time.monotonic()
        return all(vehicle.ready(now) and vehicle.state.armed and vehicle.state.mode == "OFFBOARD"
                   for vehicle in self.vehicles.values())

    def hold(self, label: str, unchanged: Vehicle | None = None) -> None:
        max_unchanged_error = 0.0

        def within():
            nonlocal max_unchanged_error
            ready = self.in_offboard()
            if unchanged is not None:
                if not ready or unchanged.error() > TOLERANCE_M:
                    self.report(f"{label}: unchanged vehicle left hold")
                    raise RuntimeError(f"Vehicle {unchanged.drone_id} left hold while vehicle 1 changed target")
                max_unchanged_error = max(max_unchanged_error, unchanged.error())
            return ready and all(vehicle.error() <= TOLERANCE_M for vehicle in self.vehicles.values())

        self.wait_for(f"{label}: reach targets", within, 45)
        deadline = time.monotonic() + HOLD_S
        next_log = 0.0
        while (now := time.monotonic()) < deadline:
            if not within():
                self.report(label)
                raise RuntimeError(f"{label}: lost hold or fresh telemetry")
            for vehicle in self.vehicles.values():
                previous = vehicle.maximum_hold_error_m.get(label, 0.0)
                vehicle.maximum_hold_error_m[label] = max(previous, vehicle.error())
            if now >= next_log:
                self.report(label)
                next_log = now + 1.0
            rclpy.spin_once(self, timeout_sec=0.05)
        if unchanged is not None:
            print(f"vehicle={unchanged.drone_id} maximum error during vehicle 1 move and hold: "
                  f"{max_unchanged_error:.3f} m", flush=True)

    def run(self) -> None:
        clients = (*self.mode_clients.values(), *self.arm_clients.values())
        self.wait_for("two fresh MAVROS streams and services",
                      lambda: all(vehicle.ready(time.monotonic()) for vehicle in self.vehicles.values())
                      and all(client.service_is_ready() for client in clients), 45)
        for vehicle in self.vehicles.values():
            if vehicle.state.armed:
                raise RuntimeError(f"Vehicle {vehicle.drone_id} is already armed; refusing to start")
            east, north, up = vehicle.position
            vehicle.desired = east, north, up + vehicle.drone_id + 1.0
        self.report("ground and distinct takeoff targets")
        prestream_until = time.monotonic() + 2.5
        self.wait_for("setpoint prestream", lambda: time.monotonic() >= prestream_until, 4)
        try:
            self.mode("OFFBOARD")
            self.wait_for("both PX4 modes OFFBOARD",
                          lambda: all(vehicle.state.mode == "OFFBOARD" for vehicle in self.vehicles.values()), 10)
            self.arm()
            self.hold("first hold")
            east, north, up = self.vehicles[1].desired
            self.vehicles[1].desired = east - 0.9, north, up
            self.report("changed only vehicle 1 desired east")
            self.hold("second hold", unchanged=self.vehicles[2])
            for vehicle in self.vehicles.values():
                print(f"vehicle={vehicle.drone_id} measured maximum hold errors (m): "
                      f"{vehicle.maximum_hold_error_m}", flush=True)
        finally:
            self.mode("AUTO.LAND")
            self.wait_for("both aircraft confirmed disarmed",
                          lambda: all(vehicle.ready(time.monotonic()) and not vehicle.state.armed
                                      for vehicle in self.vehicles.values()), 35)
            self.report("landed/disarmed")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sitl", action="store_true", required=True)
    parser.parse_args()
    rclpy.init()
    node = IndependentHold()
    try:
        node.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
