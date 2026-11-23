# SwarmNet v2 — Phases 1–2

## Ordered repair in progress

The audit is at `../docs/SwarmNet_v2_Audit_2026-10-31.txt`. Code stays in
`swarmnet_v2/`. Earlier phase scaffolding does not demonstrate working flight.
Follow `../docs/REPAIR_REPORT.md` for the current gate and evidence.

Step 1 selects PX4 **v1.16.0** (commit
`6ea3539157ca358c70a515878b77077af7d4611d`), Gazebo **Harmonic**, ROS2
**Humble**, and native Linux ARM64. Both Dockerfiles pin their Ubuntu 22.04
or ROS Humble base to an ARM64 manifest digest. PX4 is built in the image;
do not bind an unpinned host checkout over `/opt/PX4-Autopilot`.

MAPPO training will run natively on macOS in a later step. There is no
PyTorch/MPS service in Compose. Linux containers do not provide Apple Metal.

The current Docker allocation measured during repair is 10 CPUs and
7.65 GiB RAM. Service caps total 6.5 GiB (PX4 5 GiB, ROS2 1.5 GiB) and four
CPUs. For later experiments, consider 10 GiB Docker RAM on a 16 GB Mac,
leaving more than 5 GB for macOS; scale only after measurements. No Docker
Desktop allocation has been changed automatically.

The endpoint plan has no overlapping host publications: PX4 sends QGC
telemetry to `host.docker.internal:14550` on macOS; PX4 offboard local ports
are `15000+i` and ROS2 listening ports are `16000+i`, inside the bridge.
No host UDP ranges are published. These settings are a plan until Step 3
configures PX4's MAVLink startup and verifies real traffic.

Run the recorded Step 1 gate from the repository root:

```bash
./venv/bin/python swarmnet_v2/scripts/step1_gate.py --attempt 1
```

It saves command outputs in `logs/evidence/step1_*.txt`, pulls and runs both
base images, builds sequentially, records built image content IDs in
`.env.lock`, and starts the services with those IDs. Base manifest digests
and local Docker image IDs are distinct; the lock identifies local builds,
not images published to a registry. The gate must pass before Step 2.
After two failed attempts stop and inspect the evidence.

Repair checkpoint: Step 1 containers started healthy; Step 2 built all three
ROS2 packages and discovered `master_node` and `follower_node`. The state
topic contract is `/swarm/drone_<id>/state`. Two grounded SITL vehicles have
since delivered measured MAVROS pose; independent airborne hold is unverified.

**Step 3 stopped after two failed launch attempts.** The first attempt
lacked the script mount; after container recreation, PX4 failed to resolve
`etc/init.d-posix/rcS` from the startup wrapper. Step 5 fixed that startup
path, but it did not establish the Step 3 QGC and flight gate or finish the
Step 4 airborne telemetry gate. Steps 6–8 have not started.

## Step 4: measured state contract

- The follower reads pose and world-aligned local velocity, battery percentage,
  and heartbeat-derived connection state under `/drone_<id>/mavros/bridge`.
  MAVROS already converts PX4 NED telemetry to its local ENU frame. The follower
  adds the vehicle's origin to publish position in shared world ENU. It never
  adds the position offset to velocity.
- For axes aligned with the world, `world_enu = local_enu + origin_world_enu`.
  The inverse subtracts the origin. To convert local ENU `(east, north, up)`
  to PX4 NED, use `(north, east, -up)`. This assumes a fixed, aligned origin;
  if the PX4 estimator resets its origin, recalibrate and restart the follower.
- The master publishes `DesiredFormation` containing `DesiredDronePose` on
  `/swarm/desired_formation`. Positions and yaw are in world ENU (yaw is
  counterclockwise from east). The follower subtracts its origin for MAVROS
  setpoints. Desired values are not used to populate `DroneState`.
- State is published at 10 Hz even with no desired pose or incoming data.
  If any required stream is invalid or expires, or the bridge reports a
  disconnect, both `alive` and `comms_healthy` are false. Pose, velocity,
  and heartbeat expire at 2.0 s (`telemetry_timeout_s`). Battery expires
  at 5.0 s (`battery_timeout_s`) to allow for the
  [0.5 Hz PX4 MAVLink battery stream](https://github.com/PX4/PX4-Autopilot/blob/v1.16.0/src/modules/mavlink/mavlink_main.cpp#L1409).
  Age uses monotonic time since local receipt, not the ROS clock or message
  stamp. When all streams stop, expect an unhealthy update within 2.1 s of
  the last sample under normal scheduling.
  Unavailable fields are NaN (including all measurements when disconnected).
  Battery is published in percent, not fraction. The timestamp is
  publication Unix time, not sensor acquisition time.

Pass a per-node ROS parameter file to
`swarm_grid.launch.py follower_params_file:=/path/in/container/origins.yaml`.
For example, if the first vehicle's estimator origin has been verified to
coincide with the world origin:

```yaml
follower_1:
  ros__parameters:
    local_origin_world_enu: [0.0, 0.0, 0.0]
```

Calibrate each offset as a synchronized Gazebo world position minus its
MAVROS local ENU position once the estimator has settled. Do not copy
desired positions into origins. With no configured origin, world position is
unavailable and the follower sends no setpoints. No origin is auto-discovered.

The [ROS2 smoke test](scripts/step4_telemetry_smoke.py) uses explicit fixture
messages, not PX4 measurements. The remaining acceptance test is to compare
live aircraft / MAVROS movement with `/swarm/drone_1/state`, then terminate
only that PX4 process and confirm both flags drop on the next state tick
after expiry while the follower continues publishing.

## Step 5: two-vehicle SITL

With Docker Desktop running and the pinned images available locally, run from
`swarmnet_v2/`:

```bash
bash scripts/phase2-start.sh
```

This defaults to two vehicles, starts the two MAVROS bridges and formation
nodes, and leaves PX4 attached. It does not arm either vehicle. Set
`FOLLOWER_PARAMS_FILE` to a calibrated ROS parameter file inside the container
to enable follower setpoints. Leave it unset for the independent-hold
checker, which sends its own setpoints. Do not run both setpoint sources.
Stop just these services with `docker compose stop`.

| Vehicle | PX4 instance | PX4 offboard UDP | MAVROS UDP | MAVROS node | PX4 storage |
| --- | --- | --- | --- | --- | --- |
| 1 | 0 | 15000 | 16000 | `/drone_1/mavros/bridge` | `instance_0` |
| 2 | 1 | 15001 | 16001 | `/drone_2/mavros/bridge` | `instance_1` |

The first PX4 process starts Gazebo; the next attaches to that world and
spawns its own model. QGC uses one UDP listener at 14550; both PX4 instances
send to it from distinct source ports (18570 and 18571). PX4 logs and the
planned mapping are under a new directory in `logs/px4/fleet_runs/` for
each run.

The default layout fits ten columns per row, with each row centered. At
`N=50` it is **five rows × ten columns with 2 m spacing**. Spawn height is
0.15 m; the separate desired hover height is 5 m. The 254-vehicle ID
ceiling reserves 255 for GCS; it is not a performance claim. Inspect the
layout without launching any vehicles (the PX4 service must be up):

```bash
docker compose exec -T px4_sitl python3 /px4_config/scripts/drone_spawn.py --n 50 --dry-run
```

Before the next flight attempt, verify that QGC receives both vehicle IDs
and that PX4 no longer reports a missing GCS. Check any other preflight
failures rather than overriding them. When both simulators are ready,
run the SITL-only checker in a second terminal:

```bash
docker compose exec -T ros2_nodes bash -lc '
  source /opt/ros/humble/setup.bash
  source /ros2_ws/install/setup.bash
  python3 /swarmnet/scripts/step5_independent_hold.py --sitl
'
```

The checker requires two 8 s holds with measured positions within 0.35 m
of the commanded local targets. It moves only vehicle 1 and checks that vehicle 2
stays within its original tolerance throughout the move. See the repair
report for the startup evidence and the arming rejection; no hold passed.
