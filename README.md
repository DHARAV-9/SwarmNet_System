# SwarmNet_System
Autonomous Drone Swarm Simulation using Distributed Consensus Algorithms
A fully software-simulated drone swarm running on your laptop. No hardware needed.
Built with Raft consensus, Gossip protocol, and Reynolds flocking entirely in Python.

What is this?

SwarmNet simulates N drones as independent Python processes communicating over ZeroMQ sockets. Each drone elects a leader using the Raft consensus algorithm, shares world state via a Gossip protocol, and moves in formation using Reynolds flocking rules.
Kill any drone process and the swarm automatically elects a new leader and resumes formation — all within 500 ms.

Features

Raft leader election — crash-fault tolerant, quorum-based
Gossip protocol — O(log N) state convergence across all nodes
Reynolds flocking — separation, alignment, cohesion in 2D
Pygame visualizer — live top-down view of the swarm
Flask dashboard — node health, election terms, fault injection at localhost:5000
Fault injection — kill any drone or simulate packet loss
CSV metrics export — election time, gossip rounds, formation error

-How It Works

Raft leader election

Every drone starts as a follower. The leader sends heartbeats every 100 ms. If a follower receives no heartbeat within its random election timeout (150–300 ms), it becomes a candidate and requests votes from peers. The first candidate to receive a majority (⌊N/2⌋ + 1 votes) becomes the new leader. Re-election completes in under 500 ms.

Gossip protocol

Every 200 ms, each drone shares its full state table with 2 random peers. The merge rule keeps the entry with the latest timestamp per drone ID. All nodes converge to a consistent world view within O(log N) rounds.

Reynolds flocking

Each drone computes a velocity update every 50 ms using three weighted forces: separation (avoid neighbors closer than 30 units), alignment (match neighbors' average velocity), and cohesion (steer toward the group's center of mass). The leader broadcasts a waypoint via the Raft log; followers add a steering force toward their assigned formation position.

Fault tolerance
The swarm survives up to ⌊N/2⌋ simultaneous node failures (standard Raft quorum guarantee). Packet loss up to 30% is handled gracefully by gossip redundancy.

-Demo Script (for your examiner)

Run python launcher.py --n 8
Open localhost:5000 in a browser
Show the Pygame window — 8 drones moving in formation
Note the leader drone (highlighted in the visualizer)
Click "Kill Leader" in the dashboard
Show: swarm pauses briefly → new leader elected → formation resumes
Export metrics CSV and show the election time graph

