"""
launcher.py — Spawns N DroneNode processes and manages their lifecycle.

Usage:
    python launcher.py                   # Default: 5 drones
    python launcher.py --n 10            # 10 drones
    python launcher.py --n 8 --loss 0.3  # 8 drones, 30% packet loss
    python launcher.py --n 5 --seed 42   # Reproducible run

The launcher starts each drone as a subprocess running
``python -m swarmnet.core.drone_node --id <i> --n <N> ...``.
Press Ctrl+C to shut down all drones cleanly.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="SwarmNet Launcher — spawn N drone processes"
    )
    parser.add_argument(
        "--n", type=int, default=5, help="Number of drone processes (default: 5)"
    )
    parser.add_argument(
        "--base-port",
        type=int,
        default=5600,
        help="Base ZeroMQ port (default: 5600)",
    )
    parser.add_argument(
        "--loss",
        type=float,
        default=0.0,
        help="Packet loss rate 0.0–1.0 (default: 0.0)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--no-viz",
        action="store_true",
        help="Skip Pygame visualizer (Phase 3)",
    )
    parser.add_argument(
        "--no-dash",
        action="store_true",
        help="Skip Flask dashboard (Phase 4)",
    )
    return parser.parse_args()


def main() -> None:
    """Spawn drone processes and wait for Ctrl+C."""
    args = parse_args()
    n = args.n

    print("=" * 60)
    print("  SwarmNet — Autonomous Drone Swarm Simulation")
    print("  Distributed Consensus via Raft Protocol")
    print("=" * 60)
    print(f"  Drones     : {n}")
    print(f"  Packet loss: {args.loss * 100:.0f}%")
    print(f"  Seed       : {args.seed or 'random'}")
    print(f"  Visualizer : {'off' if args.no_viz else 'on'}")
    print("=" * 60)
    print()

    # Get the project root (same directory as this script)
    project_root = os.path.dirname(os.path.abspath(__file__))

    # ------------------------------------------------------------------
    # Spawn drone processes
    # ------------------------------------------------------------------
    processes: list[tuple[str, subprocess.Popen]] = []
    env = os.environ.copy()
    env["SWARMNET_BASE_PORT"] = str(args.base_port)

    print(f"[LAUNCHER] Starting {n} drone nodes...")
    for i in range(n):
        cmd = [
            sys.executable,
            "-m",
            "swarmnet.core.drone_node",
            "--id",
            str(i),
            "--n",
            str(n),
            "--loss",
            str(args.loss),
        ]
        if args.seed is not None:
            cmd.extend(["--seed", str(args.seed + i)])

        proc = subprocess.Popen(
            cmd,
            cwd=project_root,
            env=env,
            # Share stdout/stderr so terminal output is visible
        )
        processes.append((f"Drone {i}", proc))
        print(f"[LAUNCHER] Drone {i} started (PID {proc.pid})")

        # Small stagger to avoid ZeroMQ bind race conditions
        time.sleep(0.1)

    if not args.no_viz:
        cmd = [
            sys.executable,
            "-m",
            "swarmnet.viz.pygame_viz",
            "--n",
            str(n),
            "--base-port",
            str(args.base_port),
        ]
        viz_proc = subprocess.Popen(cmd, cwd=project_root, env=env)
        processes.append(("Visualizer", viz_proc))
        print(f"[LAUNCHER] Visualizer started (PID {viz_proc.pid})")

    print()
    print(f"[LAUNCHER] All {n} drones are running.")
    print("[LAUNCHER] Press Ctrl+C to shut down the swarm.")
    print()

    # ------------------------------------------------------------------
    # Wait for Ctrl+C, then shut down
    # ------------------------------------------------------------------
    try:
        while True:
            # Check if any drone has died unexpectedly
            for name, proc in processes:
                if proc.poll() is not None:
                    print(
                        f"[LAUNCHER] ⚠ {name} exited with code {proc.returncode}"
                    )
            time.sleep(1.0)
    except KeyboardInterrupt:
        print()
        print("[LAUNCHER] Shutting down all drones...")

    # Send SIGTERM to all running processes
    for _, proc in processes:
        if proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass

    # Wait for graceful shutdown (max 3 seconds)
    deadline = time.time() + 3.0
    for _, proc in processes:
        remaining = max(0.1, deadline - time.time())
        try:
            proc.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            proc.kill()

    print("[LAUNCHER] All drones stopped.")
    print("[LAUNCHER] SwarmNet session ended.")


if __name__ == "__main__":
    main()
