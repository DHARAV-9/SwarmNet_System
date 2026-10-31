# SwarmNet V2 repair evidence

Step 1 passed on attempt 2. Steps 2–8 have not started at this checkpoint.
No flight or telemetry claim is verified.

## Selected stack

Code stays in `swarmnet_v2/`. The source audit is
[SwarmNet_v2_Audit_2026-10-31.txt](SwarmNet_v2_Audit_2026-10-31.txt).

| Component | Selected immutable input |
| --- | --- |
| PX4 | `v1.16.0`, commit `6ea3539157ca358c70a515878b77077af7d4611d` |
| Gazebo | Harmonic, `gz-sim8` 8.15.0, reported by the successful native build |
| PX4 base | `ubuntu:22.04@sha256:a8fb2ba88181746111cbbe2969826d6546b71226785b196c93d2c3445a25000d` (ARM64) |
| ROS2 | Humble on Jammy |
| ROS2 base | `ros:humble-ros-base-jammy@sha256:48435c01f2876ff519a0d07edf8dd3ab29a8106c907965c64385a14c76470d6b` (ARM64) |
| Training | Deferred; native macOS Python/MPS, outside Compose |

Base images are pinned by registry manifest digest. Runtime Compose also pins
the custom images: PX4 `sha256:904f450277bc59147303be7cc0ba0006adcc8c14ea20a4c7c5efe13caf0cfeff`
and ROS2 `sha256:a36ac86fb34c495581a053a361fae8014755f2bbf6d366552ea6e933cf52110e`.
These images were built locally, not pushed to a public registry. Rebuilds use
`docker-compose.build.yml`; the gate saves local image content IDs in `.env.lock`.
APT/Python dependency versions are not a fully vendored reproducible lock.

PX4 v1.16.0's setup script explicitly installs Harmonic on Ubuntu 22.04:
[saved primary source](../swarmnet_v2/logs/evidence/step1_px4_setup_source.txt).
The release tag was resolved independently:
[release commit](../swarmnet_v2/logs/evidence/step1_px4_release.txt).

## Resources and networking

[Docker inspection](../swarmnet_v2/logs/evidence/step1_host.txt) reports
10 CPUs, 8,218,034,176 bytes (7.65 GiB), and `aarch64`.
Compose service limits are 5 GiB/3 CPUs for PX4 and 1.5 GiB/1 CPU for ROS2.
These are caps, not measured flight consumption. Other containers share the VM.

For later scaling, 10 GiB Docker RAM is a suggested setting on the stated
16 GB Mac, leaving more than 5 GB for macOS. The repair does not alter Docker
Desktop settings or stop unrelated containers.

The endpoint plan is QGC on `host.docker.internal:14550`, PX4 offboard local
`15000+i`, ROS2 offboard listener `16000+i`, inside the bridge. Compose no
longer publishes overlapping host UDP ranges. Actual PX4 routing and receipt
in QGC require Step 3 and remain unverified.

## Gate status

| Step | Status | Evidence / reason |
| --- | --- | --- |
| 1 | Passed on attempt 2 | [Attempt 2](../swarmnet_v2/logs/evidence/step1_attempt2_gate.txt) |
| 2 | Not started | Step 1 gate required |
| 3 | Not started | Step 2 gate required |
| 4 | Not started | Step 3 gate required |
| 5 | Not started | Step 4 gate required |
| 6 | Not started | Step 5 gate required |
| 7 | Not started | Step 6 gate required |
| 8 | Not started | Step 7 gate required |

Recorded Step 1 checks so far:

- [Ubuntu ARM64 manifest](../swarmnet_v2/logs/evidence/step1_ubuntu_manifest.txt)
- [ROS ARM64 manifest](../swarmnet_v2/logs/evidence/step1_ros_manifest.txt)
- [Ubuntu pull](../swarmnet_v2/logs/evidence/step1_attempt1_pull0.txt)
- [Ubuntu run: aarch64, exit 0](../swarmnet_v2/logs/evidence/step1_attempt1_run0.txt)
- [ROS pull](../swarmnet_v2/logs/evidence/step1_attempt1_pull1.txt)
- [ROS run: aarch64, exit 0](../swarmnet_v2/logs/evidence/step1_attempt1_run1.txt)
- [Compose config: exit 0](../swarmnet_v2/logs/evidence/step1_attempt1_config.txt)
- [Custom image build output](../swarmnet_v2/logs/evidence/step1_attempt1_build.txt)
- [Script syntax/diff checks: exit 0](../swarmnet_v2/logs/evidence/step1_static_checks.txt)

Attempt 1 built the ROS2 image, but PX4 dependency setup failed with
`lsb_release: command not found` (exit 127). The minimal BuildKit stage did
not trigger the upstream script's container bootstrap branch. Attempt 2
explicitly installs `lsb-release`, `sudo`, `wget`, `gnupg`, `gosu`, and
`software-properties-common` before invoking the upstream setup script.

Attempt 2 exited 0. Both bases pulled and ran as `aarch64`, both custom
images built as ARM64, and Compose reported both services healthy.
[Startup](../swarmnet_v2/logs/evidence/step1_attempt2_up.txt),
[service status](../swarmnet_v2/logs/evidence/step1_attempt2_ps.txt), and
[idle resources](../swarmnet_v2/logs/evidence/step1_attempt2_stats.txt) are saved.
Idle snapshot: PX4 880 KiB/0.02% CPU, ROS2 9.305 MiB/0.00% CPU. These
containers run `sleep infinity`; these values are not flight performance.

Highest verified flight count: **unverified; no hover demonstrated**.
N=10 real-telemetry hover for 60 seconds: **not demonstrated**.
RTF, flight RAM, flight CPU, tracking error and separation: **not measured**.

## Known defects awaiting their ordered steps

ROS2 package metadata and numeric topic tokens, fabricated follower telemetry,
arming/OFFBOARD lifecycle, frame origins, per-instance PX4 state/routing,
XRCE integration, metrics, scale tests, and the remaining document corrections
are still unresolved. Passing Step 1 would establish only image/container
readiness, not flying vehicles or working ROS2 application packages.
