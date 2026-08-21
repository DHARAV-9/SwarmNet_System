#!/usr/bin/env python3
"""Launch PX4 SITL instances at deterministic swarm grid positions."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

DEFAULT_GRID_WIDTH = 7
DEFAULT_SPACING_M = 2.0
DEFAULT_ALTITUDE_M = 5.0
DEFAULT_MAVLINK_PORT = 14550


@dataclass(frozen=True)
class DroneInstance:
    """Runtime configuration for one PX4 SITL vehicle."""

    drone_id: int
    px4_instance: int
    mavlink_port: int
    x: float
    y: float
    z: float


def grid_position(
    drone_id: int,
    grid_width: int = DEFAULT_GRID_WIDTH,
    spacing_m: float = DEFAULT_SPACING_M,
    altitude_m: float = DEFAULT_ALTITUDE_M,
) -> tuple[float, float, float]:
    """Return the TRD-defined centered grid position for a one-based ID."""
    if drone_id < 1:
        raise ValueError("drone_id must be at least 1")
    if grid_width < 1:
        raise ValueError("grid_width must be positive")
    row, col = divmod(drone_id - 1, grid_width)
    midpoint = (grid_width - 1) / 2
    return (
        (col - midpoint) * spacing_m,
        (row - midpoint) * spacing_m,
        altitude_m,
    )


def build_instances(
    n_drones: int,
    base_mavlink_port: int = DEFAULT_MAVLINK_PORT,
    grid_width: int = DEFAULT_GRID_WIDTH,
    spacing_m: float = DEFAULT_SPACING_M,
    altitude_m: float = DEFAULT_ALTITUDE_M,
) -> list[DroneInstance]:
    """Create unique IDs, MAVLink ports, and grid positions for a fleet."""
    if not 1 <= n_drones <= 50:
        raise ValueError("n_drones must be between 1 and 50")
    return [
        DroneInstance(
            drone_id=drone_id,
            px4_instance=drone_id - 1,
            mavlink_port=base_mavlink_port + drone_id - 1,
            x=grid_position(drone_id, grid_width, spacing_m, altitude_m)[0],
            y=grid_position(drone_id, grid_width, spacing_m, altitude_m)[1],
            z=altitude_m,
        )
        for drone_id in range(1, n_drones + 1)
    ]


def px4_command(px4_dir: Path, instance: DroneInstance) -> tuple[dict[str, str], list[str]]:
    """Build one PX4/Gazebo launch command with isolated instance settings."""
    environment = os.environ.copy()
    environment.update(
        {
            "PX4_SYS_AUTOSTART": "4001",
            "PX4_SIM_MODEL": "gz_x500",
            "PX4_GZ_MODEL": "x500",
            "PX4_GZ_MODEL_NAME": f"swarmnet_x500_{instance.drone_id}",
            "PX4_GZ_MODEL_POSE": f"{instance.x},{instance.y},{instance.z},0,0,0",
            "PX4_INSTANCE": str(instance.px4_instance),
            "MAV_SYS_ID": str(instance.drone_id),
            "MAVLINK_REMOTE_PORT": str(instance.mavlink_port),
        }
    )
    binary = px4_dir / "build" / "px4_sitl_default" / "bin" / "px4"
    return environment, [str(binary), "-i", str(instance.px4_instance)]


def ensure_px4_build(px4_dir: Path) -> None:
    """Build the SITL binary only when it is missing from the PX4 checkout."""
    binary = px4_dir / "build" / "px4_sitl_default" / "bin" / "px4"
    if binary.exists():
        return
    subprocess.run(["make", "px4_sitl_default"], cwd=px4_dir, check=True)


def write_manifest(instances: list[DroneInstance], log_dir: Path) -> Path:
    """Persist the generated fleet mapping for QGC and troubleshooting."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "swarm_manifest.json"
    path.write_text(
        json.dumps([asdict(instance) for instance in instances], indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def spawn(instances: list[DroneInstance], px4_dir: Path, log_dir: Path) -> None:
    """Start PX4 processes and keep them alive until interrupted."""
    processes: list[subprocess.Popen[bytes]] = []
    try:
        for instance in instances:
            environment, command = px4_command(px4_dir, instance)
            output = (log_dir / f"vehicle_{instance.drone_id}.log").open("wb")
            process = subprocess.Popen(
                command,
                cwd=px4_dir,
                env=environment,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            processes.append(process)
            print(
                f"[SPAWN] Vehicle {instance.drone_id:02d} "
                f"sys_id={instance.drone_id} qgc_udp={instance.mavlink_port} "
                f"position=({instance.x:.1f}, {instance.y:.1f}, {instance.z:.1f})"
            )
            time.sleep(0.25)
        print(f"[SPAWN] {len(processes)} PX4 SITL instances started.")
        while all(process.poll() is None for process in processes):
            time.sleep(1.0)
    finally:
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)


def parse_args() -> argparse.Namespace:
    """Parse fleet size and PX4 path options."""
    parser = argparse.ArgumentParser(description="Spawn a PX4 SITL fleet")
    parser.add_argument("--n", type=int, default=50, help="Number of drones (1-50)")
    parser.add_argument("--base-port", type=int, default=DEFAULT_MAVLINK_PORT)
    parser.add_argument("--grid-width", type=int, default=DEFAULT_GRID_WIDTH)
    parser.add_argument("--spacing", type=float, default=DEFAULT_SPACING_M)
    parser.add_argument("--altitude", type=float, default=DEFAULT_ALTITUDE_M)
    parser.add_argument(
        "--px4-dir",
        type=Path,
        default=Path(os.environ.get("PX4_DIR", "/workspace/PX4-Autopilot")),
    )
    parser.add_argument("--log-dir", type=Path, default=Path("/workspace/PX4-Autopilot/logs"))
    parser.add_argument("--dry-run", action="store_true", help="Print mapping without PX4")
    return parser.parse_args()


def main() -> None:
    """Generate the fleet mapping and optionally launch PX4 SITL."""
    args = parse_args()
    instances = build_instances(
        args.n,
        args.base_port,
        args.grid_width,
        args.spacing,
        args.altitude,
    )
    manifest = write_manifest(instances, args.log_dir)
    print(f"[SPAWN] Fleet manifest written to {manifest}")
    for instance in instances:
        print(f"[SPAWN] {instance}")
    if args.dry_run:
        return
    if not (args.px4_dir / "Tools" / "setup" / "ubuntu.sh").exists():
        raise SystemExit(f"PX4 checkout not found at {args.px4_dir}")
    ensure_px4_build(args.px4_dir)
    spawn(instances, args.px4_dir, args.log_dir)


if __name__ == "__main__":
    main()
