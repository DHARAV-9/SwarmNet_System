# SwarmNet V2 repair evidence

Step 1 passed on attempt 2. Step 2 passed its first gate attempt.
Step 3 stopped after two failed launch attempts, as required by the repair plan.
Step 4 code was started at the user's request on 2026-11-23. Its live-aircraft
gate has not passed. Step 5 verified that two grounded SITL instances sent
independent MAVROS telemetry, then stopped after two failed hold attempts.
Steps 6–8 have not started. No flight is verified.

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
and ROS2 `sha256:55ae9de19acc5eb467120926c4d80c7cca5862208367fdf5b7ee4ac61616dda3`
(activated in Step 5; includes the Step 2 geoid and Step 3 agent build).
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
| 4 | Implemented; live gate unverified | [Host tests](../swarmnet_v2/logs/evidence/step4_host_tests.txt), [ROS2 fixture test](../swarmnet_v2/logs/evidence/step4_ros_build_and_smoke.txt) |
| 5 | Two grounded streams verified; hold gate failed twice | [Attempt 1](../swarmnet_v2/logs/evidence/step5_attempt1_hold.txt), [attempt 2](../swarmnet_v2/logs/evidence/step5_attempt2_hold.txt) |
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

Arming/OFFBOARD lifecycle, calibration of live vehicle frame origins,
per-instance PX4 state/routing, XRCE integration, metrics, scale tests, and
the remaining document corrections are still unresolved. The follower's
fabricated telemetry code has been replaced; live PX4 validation is pending.

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
At the end of Step 3, the runtime image remained on the Step 2 pin. Step 5
activated the newer image for MAVROS; XRCE flight communication remains
unverified. Transitive source dependencies and APT packages are not fully locked.

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
**N=10 did not demonstrate a 60-second hover**. Step 5 corrected rcS path
resolution but did not demonstrate the Step 3 flight and QGC gate.

## Step 4 result — tested with fixtures, live gate unverified

The follower consumes MAVROS vehicle-local pose, local-frame velocity,
battery, and connection state. It publishes at 10 Hz, independent of whether
a desired pose is assigned. State and desired formation are separate
interfaces. The world ENU transform uses a calibrated per-vehicle origin;
the [measured state contract](../swarmnet_v2/README.md#step-4-measured-state-contract)
documents the setup, units, frame assumptions, and freshness thresholds
(2.0 s for pose, velocity, and heartbeat; 5.0 s for battery).
Both health flags turn false on loss of a required stream. Unavailable fields
are NaN, not fabricated position, velocity, or battery readings.

The host tests cover per-vehicle ENU/NED transforms, measurement validity,
expiry of each stream, and reconnect behavior. The
[full Python suite](../swarmnet_v2/logs/evidence/step4_full_suite.txt) passed
82 tests. The [installed MAVROS topic graph](../swarmnet_v2/logs/evidence/step4_mavros_topics.txt)
confirmed topic names and types without PX4. The isolated ROS2 test
built all three packages, exercised the real follower over DDS with fixture
inputs, verified that output moved with the input pose rather than the
desired pose, and timed the health transition when the fixtures stopped.
This did **not** verify live pose tracking or terminate a PX4 process:
no flight or real PX4-loss outcome is claimed. Highest verified flight
count and flight resource measurements are unchanged.

## Step 5 result — two grounded vehicles, independent hold unverified

PX4's positional argument must name the build's `etc` directory. PX4
symlinks it as `etc` in each instance directory; using `rootfs` previously
left `etc/init.d-posix/rcS` unresolved. Both vehicles now reached PX4's
`Startup script returned successfully`. Instance 0 started Gazebo;
instance 1 used standalone mode against the same world. Their models were
`x500_0` and `x500_1`, with separate parameters and ULog files. The
[PX4 1.16 multi-vehicle guide](https://docs.px4.io/v1.16/en/sim_gazebo_gz/multi_vehicle_simulation)
documents this first-server/later-standalone pattern.

| MAV_SYS_ID | PX4 offboard → MAVROS UDP | PX4 GCS source → QGC UDP | Startup evidence |
| --- | --- | --- | --- |
| 1 | 15000 → 16000 | 18570 → 14550 | [Vehicle 1](../swarmnet_v2/logs/evidence/step5_attempt2_vehicle1.txt) |
| 2 | 15001 → 16001 | 18571 → 14550 | [Vehicle 2](../swarmnet_v2/logs/evidence/step5_attempt2_vehicle2.txt) |

The [MAVROS log](../swarmnet_v2/logs/evidence/step5_bridges.txt) records
target IDs 1.1 and 2.1 and heartbeats from both. That verifies independent
ground telemetry, not QGC receipt or absence of airborne cross-control.
The previous ROS image digest was missing locally; the pinned ARM64
Step 3 build [started successfully](../swarmnet_v2/logs/evidence/step5_compose_up_pinned.txt).

1. [Attempt 1](../swarmnet_v2/logs/evidence/step5_attempt1_hold.txt) exited 1:
   the checker assigned to rclpy's existing read-only `Node.publishers`
   property (`AttributeError: can't set attribute 'publishers'`). It sent
   no commands. The retry renamed the attribute and corrected the GCS
   link to use PX4's default MAVLink mode.
2. [Attempt 2](../swarmnet_v2/logs/evidence/step5_attempt2_hold.txt) got measured
   pose and connected state from both bridges. Both reported OFFBOARD,
   but arming returned `success=False, result=1` and the checker exited 1.
   Both PX4 logs report `Arming denied: Resolve system health failures first`
   and `Preflight Fail: No connection to the ground control station`.
   Both vehicles remained disarmed; no landing or hover was demonstrated.

No third attempt. The next flight check requires a working QGC heartbeat
and resolution of any remaining preflight failures. The revised grid
supports up to 254 addressable vehicles (255 reserved for the GCS);
[N=50 dry run](../swarmnet_v2/logs/evidence/step5_n50_dry_run.txt) yields
5 rows × 10 columns at 2 m spacing. This proves the configuration only.
Highest verified count: **two booted and grounded; zero flown**. No flight
RTF, CPU/RAM, or hover error was measured.

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
