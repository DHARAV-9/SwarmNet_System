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
