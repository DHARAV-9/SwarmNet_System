"""Check vehicle frame math and state validity without a ROS installation."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "swarmnet_ros2" / "swarmnet_follower"))

from swarmnet_follower.frames import LocalFrame, local_enu_to_px4_ned, px4_ned_to_local_enu
from swarmnet_follower.telemetry import Telemetry


def measured():
    state = Telemetry(timeout_s=2.0)
    state.position = (2.0, -3.0, 4.0), 10.0
    state.velocity = (0.7, -0.2, 0.1), 10.0
    state.battery = 0.76, 10.0
    state.update_connection(True, 10.0)
    return state


@pytest.mark.parametrize("origin,ned", [((8., -4., 2.), (-3., 2., -4.)), ((-1., 5., -2.), (-12., 11., -8.))])
def test_world_enu_round_trips_through_each_vehicles_ned_frame(origin, ned):
    world = (10.0, -7.0, 6.0)
    frame = LocalFrame(origin)
    assert local_enu_to_px4_ned(frame.world_to_local(world)) == ned
    assert frame.local_to_world(px4_ned_to_local_enu(ned)) == world


def test_measured_position_moves_and_velocity_does_not_add_origin():
    frame = LocalFrame((8.0, -4.0, 2.0))
    state = measured()
    initial = state.snapshot(10.0, frame)
    assert initial.position == (10.0, -7.0, 6.0)
    assert initial.velocity == (0.7, -0.2, 0.1)
    assert initial.battery_percent == pytest.approx(76.0)
    assert initial.alive and initial.comms_healthy
    state.position = (5.0, -4.0, 3.0), 11.0
    assert state.snapshot(11.0, frame).position == (13.0, -8.0, 5.0)


@pytest.mark.parametrize("stale_stream", ["position", "velocity", "battery", "heartbeat"])
def test_each_stream_expires_at_its_deadline(stale_stream):
    state = measured()
    frame = LocalFrame((0.0, 0.0, 0.0))
    deadline = 15.0 if stale_stream == "battery" else 12.0
    for stream in ("position", "velocity", "battery", "heartbeat"):
        if stream != stale_stream:
            value, _ = getattr(state, stream)
            setattr(state, stream, (value, deadline - 0.01))
    assert state.snapshot(deadline - 0.001, frame).alive
    stale = state.snapshot(deadline, frame)
    assert not stale.alive and not stale.comms_healthy
    if stale_stream in ("position", "heartbeat"):
        assert all(map(math.isnan, stale.position))
    if stale_stream in ("velocity", "heartbeat"):
        assert all(map(math.isnan, stale.velocity))
    if stale_stream in ("battery", "heartbeat"):
        assert math.isnan(stale.battery_percent)


def test_disconnect_and_reconnect_does_not_reuse_old_measurements():
    state = measured()
    frame = LocalFrame((0.0, 0.0, 0.0))
    state.update_connection(False, 10.1)
    assert not state.snapshot(10.1, frame).alive
    state.update_connection(True, 10.2)
    reading = state.snapshot(10.2, frame)
    assert not reading.alive and not reading.comms_healthy
    assert all(map(math.isnan, reading.position))


def test_unknown_origin_and_invalid_measurements_are_not_reported_healthy():
    state = measured()
    assert not state.snapshot(10.0, None).alive
    frame = LocalFrame((0.0, 0.0, 0.0))
    state.battery = -1.0, 10.0
    state.position = (math.nan, 0.0, 0.0), 10.0
    reading = state.snapshot(10.0, frame)
    assert not reading.alive and not reading.comms_healthy
    assert math.isnan(reading.battery_percent)
    assert all(map(math.isnan, reading.position))
