"""Tests for Phase 2 ROS2-independent grid formation math."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "swarmnet_ros2" / "swarmnet_master"))

from swarmnet_master.formation import grid_targets


def test_grid_targets_cover_fifty_drones_with_two_meter_spacing():
    targets = grid_targets(50)

    assert len(targets) == 50
    assert targets[0].drone_id == 1
    assert targets[-1].drone_id == 50
    assert (targets[0].x, targets[0].y, targets[0].z) == (-6.0, -6.0, 5.0)
    assert (targets[1].x - targets[0].x) == 2.0
    assert (targets[7].y - targets[0].y) == 2.0
