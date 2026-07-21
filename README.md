# SwarmNet 🛸
### Autonomous Drone Swarm Simulation using Distributed Consensus Algorithms

> A fully software-simulated drone swarm running on your laptop. No hardware needed.  
> Built with Raft consensus, Gossip protocol, and Reynolds flocking — entirely in Python.

---

## What is this?

SwarmNet simulates N drones as independent Python processes communicating over ZeroMQ sockets. Each drone elects a leader using the **Raft consensus algorithm**, shares world state via a **Gossip protocol**, and moves in formation using **Reynolds flocking rules**.

Kill any drone process and the swarm automatically elects a new leader and resumes formation — all within 500 ms.

---

## Features

- **Raft leader election** — crash-fault tolerant, quorum-based
- **Gossip protocol** — O(log N) state convergence across all nodes
- **Reynolds flocking** — separation, alignment, cohesion in 2D
- **Pygame visualizer** — live top-down view of the swarm
- **Flask dashboard** — node health, election terms, fault injection at `localhost:5000`
- **Fault injection** — kill any drone or simulate packet loss
- **CSV metrics export** — election time, gossip rounds, formation error
- **Contract Net task allocation** — Raft-replicated task auctions and awards

---

## Tech Stack

| Layer | Tool |
|---|---|
| Language | Python 3.10+ |
| Messaging | ZeroMQ (pyzmq) |
| Visualization | Pygame |
| Dashboard | Flask |
| Numerics | NumPy |
| Plotting | Matplotlib |
| Testing | pytest + pytest-cov |

---

## Project Structure

```
swarmnet/
├── swarmnet/
│   ├── core/
│   │   ├── drone_node.py       # Main drone process
│   │   ├── state.py            # DroneState dataclass
│   │   └── config.py           # Loads config.ini
│   ├── consensus/
│   │   ├── raft.py             # Raft state machine
│   │   ├── log.py              # Replicated log
│   │   ├── election.py         # Vote request / response
│   │   └── heartbeat.py        # Heartbeat sender / receiver
│   ├── gossip/
│   │   ├── gossip_agent.py     # Periodic gossip loop
│   │   └── state_table.py      # World state + merge logic
│   ├── flocking/
│   │   ├── reynolds.py         # Separation, alignment, cohesion
│   │   └── formation.py        # Waypoint → per-drone targets
│   ├── tasks/
│   │   ├── allocator.py        # Contract Net task auction
│   │   └── task.py             # Task dataclass + status enum
│   ├── comms/
│   │   ├── messenger.py        # ZeroMQ socket setup
│   │   ├── serializer.py       # JSON encode / decode
│   │   └── fault_sim.py        # Packet loss injection
│   ├── viz/
│   │   ├── pygame_viz.py       # 2D Pygame subscriber
│   │   └── dashboard.py        # Flask web dashboard
│   └── metrics/
│       ├── collector.py        # Logs election time, gossip rounds
│       └── exporter.py         # CSV export + matplotlib plots
├── tests/
│   ├── test_raft.py
│   ├── test_gossip.py
│   └── test_flocking.py
├── metrics/                    # Auto-created — CSV output goes here
├── launcher.py                 # Spawns all drone processes
├── config.ini                  # All tunable parameters
├── requirements.txt
└── README.md
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/swarmnet.git
cd swarmnet
```

### 2. Create a virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Mac / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt**
```
pyzmq>=25.0
pygame>=2.5
numpy>=1.26
flask>=3.0
matplotlib>=3.8
pytest>=7.0
pytest-cov>=4.0
```

---

## Running the Simulation

### Start the swarm (default: 5 drones)

```bash
python launcher.py
```

### Custom number of drones

```bash
python launcher.py --n 10
```

### With packet loss simulation (30%)

```bash
python launcher.py --n 8 --loss 0.3
```

### Reproducible run (fixed random seed)

```bash
python launcher.py --n 5 --seed 42
```

### Without Pygame visualizer (terminal only)

```bash
python launcher.py --n 5 --no-viz
```

### All options

```
--n           Number of drone processes  (default: 5)
--base-port   Base ZeroMQ port           (default: 5600)
--loss        Packet loss rate 0.0–1.0   (default: 0.0)
--seed        Random seed                (default: None)
--no-viz      Skip Pygame window
--no-dash     Skip Flask dashboard
--dashboard-port  Flask dashboard port (default: 5000)
```

---

## Opening the Dashboard

After launching, open your browser at:

```
http://localhost:5000
```

You will see:
- Current leader ID and election term number
- Live status of every drone (alive / candidate / dead)
- Gossip convergence round count
- Battery levels
- Fault injection buttons (kill any drone, set packet loss)

## Dashboard Controls

- Use a node's **Kill** button to simulate that drone failing. The remaining
  nodes elect a replacement leader when a quorum remains.
- Select packet loss of 0%, 10%, 30%, or 50% to update every live drone at
  runtime.
- Download the combined metric CSV from the dashboard, or use the exporter
  command below for CSV plus report graphs.

## Task Allocation

Use the **New task** form in the dashboard to announce a location-based task.
After the leader commits the announcement, each drone bids using its battery
level and distance to the task. The highest bid wins, the award is replicated
through Raft, and the task becomes `in_progress` after the winning drone
confirms it. If that drone becomes unavailable for 3 seconds, the leader marks
the task failed and automatically re-announces it for a new auction.

---

## Pygame Controls

| Key | Action |
|---|---|
| `K` | Kill current leader (fault injection) |
| `W / A / S / D` | Move target waypoint |
| `1` | V-shape formation |
| `2` | Grid formation |
| `3` | Circle formation |
| `+ / -` | Increase / decrease swarm speed |
| `F` | Toggle formation overlay |
| `H` | Toggle drone ID labels |
| `Q` | Quit |

---

## Running Tests

```bash
pytest tests/ -v
```

### With coverage report

```bash
pytest --cov=swarmnet --cov-report=term-missing tests/
```

Target: **≥ 80% line coverage** on consensus, gossip, and flocking modules.

---

## Exporting Metrics

```bash
python -m swarmnet.metrics.exporter --benchmark all
```

CSV files are saved to the `metrics/` folder. Matplotlib plots (PNG) are generated automatically for:
- Election time vs swarm size
- Gossip convergence rounds vs N
- Formation error vs packet loss rate
- Message throughput per node

Run benchmark scenarios with different swarm sizes and packet-loss settings
first; the exporter combines the generated per-node CSV files and plots the
available measurements.

---

## Configuration

Edit `config.ini` to tune all parameters:

```ini
[RAFT]
HEARTBEAT_INTERVAL_MS   = 100
ELECTION_TIMEOUT_MIN_MS = 150
ELECTION_TIMEOUT_MAX_MS = 300

[GOSSIP]
GOSSIP_INTERVAL_MS = 200
GOSSIP_FANOUT      = 2

[FLOCKING]
NEIGHBOR_RADIUS = 100.0
MIN_SEP_DIST    = 30.0
MAX_SPEED       = 5.0
W_SEP = 1.5
W_ALI = 1.0
W_COH = 1.0
W_WAY = 2.0

[SIMULATION]
WORLD_WIDTH  = 800
WORLD_HEIGHT = 600
FPS          = 30
DEFAULT_N    = 5
```

---

## How It Works

### Raft leader election

Every drone starts as a follower. The leader sends heartbeats every 100 ms. If a follower receives no heartbeat within its random election timeout (150–300 ms), it becomes a candidate and requests votes from peers. The first candidate to receive a majority (`⌊N/2⌋ + 1` votes) becomes the new leader. Re-election completes in under 500 ms.

### Gossip protocol

Every 200 ms, each drone shares its full state table with 2 random peers. The merge rule keeps the entry with the latest timestamp per drone ID. All nodes converge to a consistent world view within `O(log N)` rounds.

### Reynolds flocking

Each drone computes a velocity update every 50 ms using three weighted forces: separation (avoid neighbors closer than 30 units), alignment (match neighbors' average velocity), and cohesion (steer toward the group's center of mass). The leader broadcasts a waypoint via the Raft log; followers add a steering force toward their assigned formation position.

### Fault tolerance

The swarm survives up to `⌊N/2⌋` simultaneous node failures (standard Raft quorum guarantee). Packet loss up to 30% is handled gracefully by gossip redundancy.

---

## Demo Script (for your examiner)

1. Run `python launcher.py --n 8`
2. Open `localhost:5000` in a browser
3. Show the Pygame window — 8 drones moving in formation
4. Note the leader drone (highlighted in the visualizer)
5. Click "Kill Leader" in the dashboard
6. Show: swarm pauses briefly → new leader elected → formation resumes
7. Export metrics CSV and show the election time graph

---

## Algorithms Used

| Algorithm | Purpose | Complexity |
|---|---|---|
| Raft | Leader election + log replication | O(N) messages |
| Gossip | State propagation | O(log N) rounds |
| Reynolds flocking | Formation behavior | O(N) per tick |
| Contract Net | Task allocation | O(N) per auction |

---

## Future Work

- PBFT (Byzantine fault tolerance) for adversarial environments
- 3D simulation using Gazebo or AirSim
- Real hardware deployment on Crazyflie 2.1 drones
- Reinforcement learning for dynamic path planning
- Multi-machine deployment via Docker

---

## References

- Ongaro & Ousterhout — *In Search of an Understandable Consensus Algorithm* (Raft paper)
- Craig Reynolds — *Flocks, Herds and Schools: A Distributed Behavioral Model*
- Castro & Liskov — *Practical Byzantine Fault Tolerance*
- Choi et al. — *Consensus-Based Decentralized Auctions for Robust Task Allocation*

---

## Author

**[Your Name]**  
Roll No: [Your Roll Number]  
Department of Computer Science & Engineering  
[Your College / University]  
[Year]

---

## License

MIT License — free to use, modify, and distribute for academic purposes.
