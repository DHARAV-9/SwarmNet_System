"""Tests for Phase 2 ROS2-independent grid formation math."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "swarmnet_ros2" / "swarmnet_master"))

from swarmnet_master.formation import grid_targets


def test_grid_targets_cover_fifty_drones_with_two_meter_spacing():
    targets = grid_targets(50)

    assert len(targets) == 50
    assert targets[0].drone_id == 1
    assert targets[-1].drone_id == 50
    assert (targets[0].x, targets[0].y, targets[0].z) == (-9.0, -4.0, 5.0)
    assert (targets[-1].x, targets[-1].y) == (9.0, 4.0)
    assert len({target.x for target in targets}) == 10
    assert len({target.y for target in targets}) == 5
    assert (targets[1].x - targets[0].x) == 2.0
    assert (targets[10].y - targets[0].y) == 2.0


def test_partial_row_is_centered_and_fifty_is_not_a_limit():
    targets = grid_targets(51)
    assert len(targets) == 51
    assert targets[-1].x == 0.0
    assert targets[-1].y - targets[-2].y == 2.0


@pytest.mark.parametrize("count", [0, 255])
def test_fleet_rejects_unusable_mavlink_id(count):
    with pytest.raises(ValueError, match="MAVLink"):
        grid_targets(count)
