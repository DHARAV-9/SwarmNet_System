"""Host-side tests for deterministic Phase 2 PX4 fleet configuration."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "px4_config" / "scripts" / "drone_spawn.py"
SPEC = importlib.util.spec_from_file_location("drone_spawn", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
drone_spawn = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = drone_spawn
SPEC.loader.exec_module(drone_spawn)


def test_fifty_drones_have_unique_ids_and_ports():
    fleet = drone_spawn.build_instances(50)

    assert [drone.drone_id for drone in fleet] == list(range(1, 51))
    assert [drone.mavlink_port for drone in fleet] == list(range(14550, 14600))
    assert len({drone.px4_instance for drone in fleet}) == 50


def test_grid_is_centered_with_two_meter_spacing():
    fleet = drone_spawn.build_instances(50)

    assert (fleet[0].x, fleet[0].y, fleet[0].z) == (-6.0, -6.0, 5.0)
    assert (fleet[6].x, fleet[6].y) == (6.0, -6.0)
    assert (fleet[7].x, fleet[7].y) == (-6.0, -4.0)
    assert (fleet[-1].x, fleet[-1].y) == (-6.0, 8.0)
