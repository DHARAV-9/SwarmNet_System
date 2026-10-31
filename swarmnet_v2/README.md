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

The older instructions below describe the pre-repair scaffold and are
unverified. Do not use the old Phase 2 launcher while the repair gate is open.

Repair checkpoint: Step 1 containers started healthy; Step 2 built all three
ROS2 packages and discovered `master_node` and `follower_node`. The state
topic contract is `/swarm/drone_<id>/state`. Flight and measured telemetry
remain unverified; see the evidence-linked report above.

**Stopped at Step 3 after two failed launch attempts.** The first attempt
lacked the script mount; after container recreation, PX4 failed to resolve
`etc/init.d-posix/rcS` from the startup wrapper. No vehicle flew and QGC
remained disconnected. Steps 4–8 have not started. The new `step3_start.sh`
and `flight_cycle.py` are unverified; do not treat them as working demos.

Phase 1 brings up one PX4 SITL X500 drone in Gazebo, connects it to native
macOS QGroundControl, and prepares the three-container network used by later
swarm phases.

## Host setup (macOS)

1. Install Docker Desktop for Apple Silicon and start it.
2. In Docker Desktop → Settings → Resources, set **8 CPUs** and **12 GB RAM**.
3. Enable Rosetta emulation in Docker Desktop; the PX4 development image
   defaults to `linux/amd64` in `.env` for broad compatibility.
4. Install XQuartz, restart macOS, then open it:

```bash
brew install --cask xquartz
open -a XQuartz
xhost +localhost
```

5. Install QGroundControl for macOS Apple Silicon.

## Prepare source and images

```bash
cd /Users/dharavbhatt/swaram_net/swarmnet_v2
cp .env.example .env
git clone --recursive https://github.com/PX4/PX4-Autopilot.git
docker compose pull
./scripts/phase1-doctor.sh
```

## Start one drone

```bash
docker compose up -d
docker compose exec px4_sitl bash /px4_config/scripts/spawn_one_drone.sh
```

The second command remains attached to PX4/Gazebo. Keep it running while you
test the vehicle. Set `HEADLESS=1` in `.env` if XQuartz forwarding is slow.

## Verify QGroundControl

In QGroundControl: **Application Settings → Comm Links → Add → UDP**, use port
`14550` and host `localhost`. One vehicle should appear. Arm and disarm it from
QGroundControl, then run this from another terminal:

```bash
cd /Users/dharavbhatt/swaram_net/swarmnet_v2
./scripts/phase1-verify.sh
```

## Stop

```bash
docker compose down
```

## Phase 2 — 50-drone grid formation

Phase 2 starts 50 PX4 SITL instances, assigns IDs `1–50`, maps QGroundControl
ports `14550–14599`, and publishes a static 7-column grid formation at 2 m
spacing and 5 m altitude. A 7×7 grid has 49 slots, so vehicle 50 occupies the
first slot of a final partial row. Vehicle 1 is the master; remaining vehicles
are followers.

### Run the 50-drone fleet

Set `N_DRONES=50` in `.env`, then run:

```bash
cd /Users/dharavbhatt/swaram_net/swarmnet_v2
./scripts/phase2-start.sh
```

For a safer smoke test first, set `N_DRONES=1` in `.env`, start the fleet, then
return it to `50` once PX4, Gazebo, QGroundControl, and XQuartz work normally.

### Verify the planned launch before starting PX4

```bash
python3 px4_config/scripts/drone_spawn.py --n 50 --dry-run
python3 -m pytest tests/ -v
```

The generated `logs/px4/swarm_manifest.json` records each drone's PX4 instance,
MAVLink port, and initial position.

### QGroundControl and ROS2 checks

Configure one UDP connection per vehicle in QGroundControl on ports
`14550–14599`. Then run:

```bash
./scripts/phase2-verify.sh
python3 scripts/profile_resources.py --duration 60 --budget-gb 14
```

Phase 2 is accepted only when all 50 vehicles remain visible and stable in the
grid, no PX4 process exits, and the profiling command reports peak RAM below
14 GiB.
