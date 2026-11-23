"""Verify the follower over ROS2 with test fixtures, not aircraft telemetry."""

import math
import time

import rclpy
from geometry_msgs.msg import PoseStamped, TwistStamped
from mavros_msgs.msg import State
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import BatteryState
from swarmnet_msgs.msg import DesiredDronePose, DesiredFormation, DroneState

from swarmnet_follower.follower_node import FollowerNode


def run_check(executor: SingleThreadedExecutor, fixture: Node) -> None:
    prefix = "/drone_1/mavros/bridge"
    pose_pub = fixture.create_publisher(PoseStamped, f"{prefix}/local_position/pose", qos_profile_sensor_data)
    velocity_pub = fixture.create_publisher(TwistStamped, f"{prefix}/local_position/velocity_local", qos_profile_sensor_data)
    battery_pub = fixture.create_publisher(BatteryState, f"{prefix}/battery", qos_profile_sensor_data)
    heartbeat_pub = fixture.create_publisher(State, f"{prefix}/state", qos_profile_sensor_data)
    desired_pub = fixture.create_publisher(
        DesiredFormation, "/swarm/desired_formation",
        QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
    )
    states = []
    setpoints = []
    fixture.create_subscription(DroneState, "/swarm/drone_1/state", states.append, 10)
    fixture.create_subscription(PoseStamped, f"{prefix}/setpoint_position/local", setpoints.append, 10)
    print("Source: ROS2 test fixtures; no PX4 or MAVROS aircraft data", flush=True)

    def wait_for(condition, send=None, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if send is not None:
                send()
            executor.spin_once(timeout_sec=0.02)
            if condition():
                return
        raise AssertionError("Timed out waiting for expected ROS2 output")

    wait_for(lambda: bool(states))
    assert not states[-1].alive and not states[-1].comms_healthy
    assert math.isnan(states[-1].x)
    desired_pub.publish(DesiredFormation(targets=[DesiredDronePose(drone_id=1, x=100.0, y=90.0, z=20.0)]))
    pose = PoseStamped()
    pose.header.frame_id = "map"
    pose.pose.position.x = 2.0
    pose.pose.position.y = -3.0
    pose.pose.position.z = 4.0
    velocity = TwistStamped()
    velocity.header.frame_id = "map"
    velocity.twist.linear.x = 0.7

    def send_measurements():
        pose_pub.publish(pose)
        velocity_pub.publish(velocity)
        battery_pub.publish(BatteryState(percentage=0.76))
        heartbeat_pub.publish(State(connected=True))

    wait_for(lambda: states[-1].alive and bool(setpoints), send_measurements)
    reading = states[-1]
    assert reading.comms_healthy
    assert (reading.x, reading.y, reading.z) == (10.0, -7.0, 6.0)
    assert (reading.vx, reading.vy, reading.vz) == (0.7, 0.0, 0.0)
    assert math.isclose(reading.battery, 76.0, abs_tol=0.001)
    setpoint = setpoints[-1].pose.position
    assert (setpoint.x, setpoint.y, setpoint.z) == (92.0, 94.0, 18.0)
    print(f"Measured world pose: {(reading.x, reading.y, reading.z)}; desired local pose: "
          f"{(setpoint.x, setpoint.y, setpoint.z)}; battery: {reading.battery:.1f}%", flush=True)
    pose.pose.position.x = 5.0
    wait_for(lambda: states[-1].x == 13.0 and states[-1].alive, send_measurements)
    print(f"Updated reported world x: {states[-1].x:.1f} m", flush=True)

    stopped_at = time.monotonic()
    wait_for(lambda: not states[-1].alive and not states[-1].comms_healthy, timeout=2.5)
    elapsed = time.monotonic() - stopped_at
    print(f"After fixture stream stopped: alive=false comms_healthy=false in {elapsed:.3f} s", flush=True)
    wait_for(lambda: all(math.isnan(value) for value in (states[-1].x, states[-1].vx, states[-1].battery)))


def main() -> None:
    rclpy.init(args=["--ros-args", "-p", "local_origin_world_enu:=[8.0, -4.0, 2.0]"])
    executor = SingleThreadedExecutor()
    follower = FollowerNode()
    fixture = Node("step4_telemetry_fixture")
    try:
        executor.add_node(follower)
        executor.add_node(fixture)
        run_check(executor, fixture)
    finally:
        executor.shutdown()
        fixture.destroy_node()
        follower.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
