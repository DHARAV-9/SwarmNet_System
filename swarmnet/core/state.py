"""
state.py — DroneState dataclass.

Single source of truth for all per-drone state.  Every drone process holds
exactly one DroneState instance that is read and mutated by the Raft state
machine, gossip agent, flocking engine, and task allocator.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DroneState:
    """Complete mutable state for a single drone node.

    Attributes:
        drone_id:      Unique integer identifier (0 … N-1).
        x, y:          Current 2-D position in simulation units.
        vx, vy:        Current velocity vector.
        battery:       Simulated battery level (100.0 → 0.0).
        raft_state:    One of ``"follower"``, ``"candidate"``, ``"leader"``.
        current_term:  Monotonically increasing Raft term counter.
        voted_for:     Candidate ID this node voted for in the current term,
                       or ``None`` if no vote has been cast.
        log:           Local Raft replicated log (list of dicts).
        commit_index:  Highest log index known to be committed.
        last_applied:  Highest log index applied to the state machine.
        next_index:    (Leader only) next log index to send to each peer.
        match_index:   (Leader only) highest log index replicated per peer.
        task:          Currently assigned task identifier, or ``None``.
        alive:         ``False`` if this node has been killed / shut down.
        leader_id:     The ID of the current known leader, or ``None``.
        last_heartbeat: Timestamp (monotonic) of last received heartbeat.
        votes_received: Set of drone IDs that voted for this node (candidate).
        peers:         List of all peer drone IDs in the cluster.
    """

    # --- Identity ---
    drone_id: int

    # --- Position & kinematics ---
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0

    # --- Simulation ---
    battery: float = 100.0
    task: Optional[str] = None
    alive: bool = True

    # --- Raft persistent state ---
    raft_state: str = "follower"
    current_term: int = 0
    voted_for: Optional[int] = None
    log: list = field(default_factory=list)

    # --- Raft volatile state ---
    commit_index: int = 0
    last_applied: int = 0

    # --- Raft leader-only volatile state ---
    next_index: dict = field(default_factory=dict)
    match_index: dict = field(default_factory=dict)

    # --- Runtime bookkeeping ---
    leader_id: Optional[int] = None
    last_heartbeat: float = field(default_factory=time.monotonic)
    votes_received: set = field(default_factory=set)
    peers: list = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def reset_election_state(self) -> None:
        """Clear vote-related fields when reverting to follower."""
        self.voted_for = None
        self.votes_received = set()

    def become_follower(self, term: int) -> None:
        """Transition to follower for *term*, resetting election state."""
        self.raft_state = "follower"
        self.current_term = term
        self.reset_election_state()
        self.last_heartbeat = time.monotonic()

    def become_candidate(self) -> None:
        """Transition to candidate: increment term, vote for self."""
        self.raft_state = "candidate"
        self.current_term += 1
        self.voted_for = self.drone_id
        self.votes_received = {self.drone_id}
        self.leader_id = None
        self.last_heartbeat = time.monotonic()

    def become_leader(self) -> None:
        """Transition to leader after winning an election."""
        self.raft_state = "leader"
        self.leader_id = self.drone_id
        # Initialize next_index and match_index for all peers
        last_log_idx = len(self.log)
        for peer_id in self.peers:
            self.next_index[peer_id] = last_log_idx + 1
            self.match_index[peer_id] = 0

    def has_majority(self, n_total: int) -> bool:
        """Return ``True`` if votes_received constitutes a quorum."""
        return len(self.votes_received) >= (n_total // 2) + 1

    def to_broadcast_dict(self) -> dict:
        """Return a dict suitable for the state_broadcast PUB message."""
        return {
            "type": "state_broadcast",
            "drone_id": self.drone_id,
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "raft_state": self.raft_state,
            "term": self.current_term,
            "battery": self.battery,
            "leader_id": self.leader_id,
            "task": self.task,
        }
