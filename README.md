# SwarmNet_System
Autonomous Drone Swarm Simulation using Distributed Consensus Algorithms
A fully software-simulated drone swarm running on your laptop. No hardware needed.
Built with Raft consensus, Gossip protocol, and Reynolds flocking entirely in Python.

What is this?

SwarmNet simulates N drones as independent Python processes communicating over ZeroMQ sockets. Each drone elects a leader using the Raft consensus algorithm, shares world state via a Gossip protocol, and moves in formation using Reynolds flocking rules.
Kill any drone process and the swarm automatically elects a new leader and resumes formation — all within 500 ms.
