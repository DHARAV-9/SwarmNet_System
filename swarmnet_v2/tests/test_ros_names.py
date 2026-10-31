"""Check generated topic names without requiring host ROS2."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "swarmnet_ros2" / "swarmnet_follower"))

from swarmnet_follower.topics import state_topic


def test_all_fleet_state_topics_are_distinct_valid_ros_names():
    names = [state_topic(drone_id) for drone_id in range(1, 51)]
    assert len(set(names)) == 50
    for name in names:
        assert all(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token) for token in name.split("/")[1:])
    assert names[0] == "/swarm/drone_1/state"


@pytest.mark.parametrize("drone_id", [0, -1, True, "1"])
def test_invalid_drone_ids_are_rejected(drone_id):
    with pytest.raises(ValueError):
        state_topic(drone_id)
