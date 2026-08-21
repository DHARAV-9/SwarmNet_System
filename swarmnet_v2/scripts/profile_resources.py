#!/usr/bin/env python3
"""Record Docker container RAM/CPU usage and enforce the Phase 2 RAM budget."""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import time
from pathlib import Path

CONTAINERS = ("swarmnet_px4", "swarmnet_ros2", "swarmnet_ai")
UNITS = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}


def bytes_from_docker(value: str) -> float:
    """Convert Docker's human-readable memory values to bytes."""
    match = re.fullmatch(r"\s*([0-9.]+)\s*(B|KiB|MiB|GiB)\s*", value)
    if match is None:
        raise ValueError(f"unsupported Docker memory value: {value!r}")
    return float(match.group(1)) * UNITS[match.group(2)]


def sample() -> list[dict[str, str]]:
    """Return one Docker stats snapshot for all Phase 2 containers."""
    command = [
        "docker",
        "stats",
        "--no-stream",
        "--format",
        "{{.Name}},{{.CPUPerc}},{{.MemUsage}}",
        *CONTAINERS,
    ]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    rows: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        name, cpu_percent, memory = line.split(",", maxsplit=2)
        used, limit = (part.strip() for part in memory.split("/", maxsplit=1))
        rows.append(
            {
                "container": name,
                "cpu_percent": cpu_percent.rstrip("%"),
                "memory_bytes": str(int(bytes_from_docker(used))),
                "memory_limit_bytes": str(int(bytes_from_docker(limit))),
            }
        )
    return rows


def main() -> None:
    """Sample for a configured duration and fail when peak RAM exceeds budget."""
    parser = argparse.ArgumentParser(description="Profile SwarmNet V2 Docker resources")
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--budget-gb", type=float, default=14.0)
    parser.add_argument("--output", type=Path, default=Path("logs/resources_phase2.csv"))
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.duration
    peak_bytes = 0.0
    with args.output.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=["timestamp", "container", "cpu_percent", "memory_bytes", "memory_limit_bytes"],
        )
        writer.writeheader()
        while True:
            rows = sample()
            timestamp = time.time()
            peak_bytes = max(peak_bytes, sum(float(row["memory_bytes"]) for row in rows))
            for row in rows:
                writer.writerow({"timestamp": timestamp, **row})
            if time.monotonic() >= deadline:
                break
            time.sleep(args.interval)
    peak_gb = peak_bytes / (1024**3)
    print(f"Peak Phase 2 Docker RAM: {peak_gb:.2f} GiB")
    if peak_gb > args.budget_gb:
        raise SystemExit(f"RAM budget exceeded: {peak_gb:.2f} GiB > {args.budget_gb:.2f} GiB")


if __name__ == "__main__":
    main()
