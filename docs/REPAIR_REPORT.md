# SwarmNet V2 repair evidence

Step 1 passed on attempt 2. Step 2 passed its first gate attempt.
Step 3 stopped after two failed launch attempts, as required by the repair plan.
Steps 4–8 have not started because Step 3 did not pass.
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
and ROS2 `sha256:428618639cda845890386ef1b5e38604309ce3652c488022addae296942b8deb`
(updated in Step 2 to include the required EGM96 geoid dataset).
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
| 2 | Passed on attempt 1 | [Container build/discovery](../swarmnet_v2/logs/evidence/step2_attempt1_gate.txt) |
| 3 | Failed twice; stopped | [Attempt 1](../swarmnet_v2/logs/evidence/step3_attempt1_px4_launch.txt), [attempt 2](../swarmnet_v2/logs/evidence/step3_attempt2_px4_launch.txt) |
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

Fabricated follower telemetry, arming/OFFBOARD lifecycle, frame origins,
per-instance PX4 state/routing,
XRCE integration, metrics, scale tests, and the remaining document corrections
are still unresolved. Passing Step 1 would establish only image/container
readiness, not flying vehicles or working ROS2 application packages.

## Step 3 result — stopped, not passed

Two launch attempts failed. No further flight attempts or later repair steps
were performed after the second failure.

1. Attempt 1 exited **2** before PX4 ran:
   `python3: can't open file '/swarmnet/scripts/capture_evidence.py': [Errno 2] No such file or directory`.
   The existing container had not been recreated with the new read-only script
   mount. Recreating only the PX4 service succeeded; a subsequent preflight
   confirmed the script was readable and both shell scripts parsed.
   [Recreation](../swarmnet_v2/logs/evidence/step3_attempt1_mount_repair.txt),
   [preflight](../swarmnet_v2/logs/evidence/step3_launch_preflight.txt).
2. Attempt 2 launched PX4 instance 0, then exited **255**:
   `/px4_config/scripts/swarm_startup.sh: 2: .: cannot open etc/init.d-posix/rcS: No such file`.
   PX4 also reported `Startup script returned with return value: 512`.
   The launcher supplied the compiled rootfs positional argument and a separate
   instance working directory, but the wrapper's relative rcS path did not
   resolve. The correct startup root/path contract remains to be repaired.
   [PX4's own output](../swarmnet_v2/logs/evidence/step3_attempt2_vehicle_runtime.txt).

Written but **unverified**: startup commands for system ID, non-overlapping
MAVLink endpoints and XRCE namespace; first-instance/standalone selection;
and the telemetry-driven arm/OFFBOARD/takeoff/hover/land/disarm script.
The failure occurred before these startup commands were consumed. Do not
interpret their presence in source as proof of working routing or lifecycle.

The native source image containing Micro XRCE-DDS Agent v2.4.3
(`73622810d984349b80bbac0ef55fc0b694d62222`) and PX4 messages from release/1.16
(`392e831c1f659429ca83902e66820d7094591410`) built successfully in the initial
layout: [build](../swarmnet_v2/logs/evidence/step3_attempt1_image_build.txt).
A corrected workspace-location image rebuild was started before the failed
launches and completed successfully (exit 0, `px4_msgs` built in 91 seconds).
Its build manifest digest is
`sha256:55ae9de19acc5eb467120926c4d80c7cca5862208367fdf5b7ee4ac61616dda3`;
it is a build artifact, not the currently activated runtime image. Its output is in
[workspace build](../swarmnet_v2/logs/evidence/step3_workspace_image_build.txt).
The Compose runtime ROS image remains pinned to the verified **Step 2 image**;
the Step 3 agent image has not been activated or verified communicating with
PX4. Transitive source dependencies and APT packages are not fully locked.

Official QGroundControl **v5.1.5** was downloaded, SHA256 checked against its
release asset, mounted read-only and launched. Its executable contains ARM64.
The observed UI said **Disconnected**; no vehicle telemetry was demonstrated.
It runs from `/private/tmp/swarmnet-qgc-515/QGroundControl.app`, not a permanent
installation. [Checksum](../swarmnet_v2/logs/evidence/step3_qgc_checksum.txt),
[architecture](../swarmnet_v2/logs/evidence/step3_qgc_binary.txt),
[launch](../swarmnet_v2/logs/evidence/step3_qgc_launch.txt).
The disconnected UI observation is recorded separately as a human-readable
[UI inspection](../swarmnet_v2/logs/evidence/step3_qgc_ui_observation.txt),
not misrepresented as command stdout or successful vehicle telemetry.

Highest verified N: **no flying vehicle**. No arm, takeoff, hover, landing,
disarm, RTF or flight resource measurement was collected. In particular,
**N=10 did not demonstrate a 60-second hover**. The next authorized repair
should first fix and prove rcS/rootfs resolution, then activate the agent
image and retry the Step 3 gate; Steps 4–8 remain blocked behind that gate.

## Step 2 result

The native ROS2 image rebuilt with `/usr/share/GeographicLib/geoids/egm96-5.pgm`:
[image build](../swarmnet_v2/logs/evidence/step2_attempt1_build.txt).
Both Python packages now install executables under `lib/<package>` and export
`ament_python`; the message package exports `ament_cmake`.
The container command reported:

```text
Summary: 3 packages finished [13.0s]
swarmnet_master master_node
swarmnet_follower follower_node
EXIT_STATUS: 0
```

The state topic contract is `/swarm/drone_<id>/state`, also corrected in the
PRD/TRD and verifier. Five host naming tests passed:
[tests](../swarmnet_v2/logs/evidence/step2_host_tests.txt).
This gate verifies building and executable discovery, not real telemetry.

## Commit history note

Step 1 changes were committed externally during this repair as `1a14d28`
(`bug_fix`). The requested Step 1 commit command found a clean worktree.
That existing commit was preserved without rewriting history. Subsequent
repair commits use the requested `fix(step N):` prefix.
