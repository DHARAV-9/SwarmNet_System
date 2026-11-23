"""Host-side tests for deterministic Phase 2 PX4 fleet configuration."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "px4_config" / "scripts" / "drone_spawn.py"
sys.path.insert(0, str(Path(__file__).parents[1] / "swarmnet_ros2" / "swarmnet_master"))
SPEC = importlib.util.spec_from_file_location("drone_spawn", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
drone_spawn = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = drone_spawn
SPEC.loader.exec_module(drone_spawn)


def test_fifty_drones_have_unique_ids_and_ports():
    fleet = drone_spawn.build_instances(50)

    assert [drone.route.drone_id for drone in fleet] == list(range(1, 51))
    assert len({drone.route.instance for drone in fleet}) == 50
    assert len({drone.route.namespace for drone in fleet}) == 50
    assert len({drone.route.state_dir for drone in fleet}) == 50
    assert len({port for drone in fleet for port in (
        drone.route.offboard_port, drone.route.mavros_port, drone.route.gcs_source_port
    )}) == 150


def test_two_vehicles_share_grid_but_not_routing_or_storage(tmp_path):
    first, second = drone_spawn.build_instances(2)
    assert first.spawn_xyz == (-1.0, 0.0, 0.15)
    assert second.spawn_xyz == (1.0, 0.0, 0.15)
    assert first.target.z == second.target.z == 5.0
    assert first.route.fcu_url("px4_sitl") == "udp://:16000@px4_sitl:15000"
    assert second.route.fcu_url("px4_sitl") == "udp://:16001@px4_sitl:15001"
    first_env, command = drone_spawn.px4_command(tmp_path, first)
    second_env, _ = drone_spawn.px4_command(tmp_path, second)
    assert command[-1].endswith("spawn_one_drone.sh")
    for index, env in enumerate((first_env, second_env)):
        assert env["PX4_INSTANCE"] == str(index)
        assert env["SWARM_STATE_DIR"] == str(tmp_path / f"instance_{index}")
        assert env["SWARM_OFFBOARD_PORT"] == str(15000 + index)
        assert env["SWARM_MAVROS_PORT"] == str(16000 + index)
        assert env["QGC_PORT"] == "14550"


def test_mavlink_boundary_has_no_port_overlap():
    fleet = drone_spawn.build_instances(254)
    plan = drone_spawn.manifest(fleet)
    assert len(plan) == 254
    assert len({vehicle[key] for vehicle in plan for key in (
        "px4_offboard_port", "mavros_port", "px4_gcs_source_port"
    )}) == 3 * 254
