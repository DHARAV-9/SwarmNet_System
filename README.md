# SwarmNet v2 — Phases 1–2

> Repair status (2026-10-31): Steps 1–2 passed; Step 3 stopped after two
> failed launches. No flight is verified. The instructions below predate
> the repair; use [the evidence report](docs/REPAIR_REPORT.md) and
> [current repair notes](swarmnet_v2/README.md), not the old demo claims.

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


