#!/usr/bin/env python3
"""Launch PX4 SITL fleet instances with the same routing and grid as ROS2."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from swarmnet_master.formation import (
    DEFAULT_ALTITUDE_M,
    DEFAULT_GRID_WIDTH,
    DEFAULT_SPACING_M,
    FormationTarget,
    grid_targets,
)
from swarmnet_master.routing import QGC_PORT, VehicleRoute

SPAWN_HEIGHT_M = 0.15
DEFAULT_RUNS_DIR = Path("/var/log/swarmnet/px4/fleet_runs")


@dataclass(frozen=True)
class DroneInstance:
    route: VehicleRoute
    target: FormationTarget

    @property
    def spawn_xyz(self) -> tuple[float, float, float]:
        return self.target.x, self.target.y, SPAWN_HEIGHT_M


def build_instances(n_drones: int, grid_width: int = DEFAULT_GRID_WIDTH,
                    spacing_m: float = DEFAULT_SPACING_M,
                    altitude_m: float = DEFAULT_ALTITUDE_M) -> list[DroneInstance]:
    return [DroneInstance(VehicleRoute(target.drone_id), target)
            for target in grid_targets(n_drones, grid_width, spacing_m, altitude_m)]


def px4_command(directory: Path, drone: DroneInstance) -> tuple[dict[str, str], list[str]]:
    route = drone.route
    east, north, up = drone.spawn_xyz
    environment = {
        **os.environ,
        "PX4_INSTANCE": str(route.instance),
        "PX4_GZ_MODEL_POSE": f"{east},{north},{up},0,0,0",
        "SWARM_STATE_DIR": str(directory / route.state_dir),
        "SWARM_OFFBOARD_PORT": str(route.offboard_port),
        "SWARM_MAVROS_PORT": str(route.mavros_port),
        "SWARM_GCS_SOURCE_PORT": str(route.gcs_source_port),
        "QGC_PORT": str(QGC_PORT),
    }
    return environment, ["bash", str(Path(__file__).with_name("spawn_one_drone.sh"))]


def manifest(fleet: list[DroneInstance]) -> list[dict]:
    return [
        {
            "drone_id": drone.route.drone_id,
            "px4_instance": drone.route.instance,
            "px4_offboard_port": drone.route.offboard_port,
            "mavros_port": drone.route.mavros_port,
            "px4_gcs_source_port": drone.route.gcs_source_port,
            "qgc_port": QGC_PORT,
            "mavros_namespace": drone.route.namespace,
            "state_dir": drone.route.state_dir,
            "spawn_world_enu": drone.spawn_xyz,
            "desired_world_enu": (drone.target.x, drone.target.y, drone.target.z),
        }
        for drone in fleet
    ]


def check_running(processes: dict[int, subprocess.Popen]) -> None:
    for drone_id, process in processes.items():
        if (status := process.poll()) is not None:
            raise RuntimeError(f"PX4 vehicle {drone_id} exited with code {status}")


def spawn(fleet: list[DroneInstance], directory: Path) -> None:
    processes: dict[int, subprocess.Popen] = {}
    try:
        for drone in fleet:
            route = drone.route
            env, command = px4_command(directory, drone)
            path = directory / f"vehicle_{route.drone_id}.log"
            with path.open("xb") as output:
                processes[route.drone_id] = subprocess.Popen(
                    command, env=env, stdout=output, stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            marker = f"SwarmNet PX4 instance {route.instance} ready"
            deadline = time.monotonic() + 90
            while marker not in path.read_text(errors="replace"):
                check_running(processes)
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"PX4 vehicle {route.drone_id} startup timed out; see {path}")
                time.sleep(0.2)
            print(f"Vehicle {route.drone_id} completed PX4 startup; log: {path}", flush=True)
        print(f"{len(processes)} PX4 vehicles started; flight not yet verified", flush=True)
        while True:
            check_running(processes)
            time.sleep(0.5)
    finally:
        for process in processes.values():
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for process in processes.values():
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def stop_on_signal(signum, frame) -> None:
    raise KeyboardInterrupt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=2)
    parser.add_argument("--grid-width", type=int, default=DEFAULT_GRID_WIDTH)
    parser.add_argument("--spacing", type=float, default=DEFAULT_SPACING_M)
    parser.add_argument("--altitude", type=float, default=DEFAULT_ALTITUDE_M)
    parser.add_argument("--log-dir", type=Path, help="New directory for this run")
    parser.add_argument("--dry-run", action="store_true", help="Print the plan without starting PX4")
    args = parser.parse_args()
    try:
        fleet = build_instances(args.n, args.grid_width, args.spacing, args.altitude)
    except ValueError as error:
        parser.error(str(error))
    plan = json.dumps(manifest(fleet), indent=2)
    if args.dry_run:
        print(plan)
        return
    if args.log_dir is None:
        DEFAULT_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="run_", dir=DEFAULT_RUNS_DIR))
    else:
        directory = args.log_dir.resolve()
        directory.mkdir(parents=True)
    (directory / "swarm_manifest.json").write_text(plan + "\n", encoding="utf-8")
    print(f"Planned fleet: {directory / 'swarm_manifest.json'}", flush=True)
    signal.signal(signal.SIGTERM, stop_on_signal)
    try:
        spawn(fleet, directory)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
