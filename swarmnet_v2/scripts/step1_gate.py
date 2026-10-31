"""Execute and record the Step 1 stack gate, stopping at the first failure."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "scripts" / "capture_evidence.py"
BASES = (
    "ubuntu:22.04@sha256:a8fb2ba88181746111cbbe2969826d6546b71226785b196c93d2c3445a25000d",
    "ros:humble-ros-base-jammy@sha256:48435c01f2876ff519a0d07edf8dd3ab29a8106c907965c64385a14c76470d6b",
)


def run(label: str, command: list[str], attempt: int) -> None:
    """Run a command through the recorder, preserving its exit status."""
    path = ROOT / "logs" / "evidence" / f"step1_attempt{attempt}_{label}.txt"
    subprocess.run(
        [sys.executable, str(CAPTURE), str(path), "--", *command],
        cwd=ROOT,
        check=True,
    )


def main() -> None:
    """Pull bases, build, pin local content IDs, and start every service."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    attempt = args.attempt
    run("config", ["docker", "compose", "config", "--quiet"], attempt)
    for index, image in enumerate(BASES):
        run(f"pull{index}", ["docker", "pull", "--platform", "linux/arm64", image], attempt)
        run(
            f"run{index}",
            ["docker", "run", "--rm", "--platform", "linux/arm64", image,
             "bash", "-lc", "uname -m; test \"$(dpkg --print-architecture)\" = arm64"],
            attempt,
        )
    run("build", ["docker", "compose", "-f", "docker-compose.build.yml", "--parallel", "1", "--progress", "plain", "build"], attempt)
    records = {}
    for key, image in (
        ("PX4_IMAGE", "swarmnet/px4-sitl:v1.16.0-arm64"),
        ("ROS_IMAGE", "swarmnet/ros2-nodes:humble-arm64"),
    ):
        inspection = json.loads(subprocess.check_output(["docker", "image", "inspect", image]))[0]
        if inspection["Architecture"] != "arm64":
            raise RuntimeError(f"Unexpected architecture for {image}")
        records[key] = inspection["Id"]
        run(key.lower(), ["docker", "image", "inspect", image], attempt)
    lock = ROOT / ".env.lock"
    lock.write_text("".join(f"{key}={value}\n" for key, value in records.items()), encoding="utf-8")
    compose = ["docker", "compose", "--env-file", str(lock)]
    run("locked_config", [*compose, "config"], attempt)
    run("up", [*compose, "up", "-d", "--no-build", "--pull", "never", "--wait"], attempt)
    run("ps", [*compose, "ps"], attempt)
    run("stats", ["docker", "stats", "--no-stream", "swarmnet_px4", "swarmnet_ros2"], attempt)
    print("STEP 1 STACK GATE PASSED. Flight remains unverified.")


if __name__ == "__main__":
    main()
