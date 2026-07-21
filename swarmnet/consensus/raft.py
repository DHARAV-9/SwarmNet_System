"""
raft.py — Raft state machine orchestrator.

Ties together election, heartbeat, and log modules into a single ``tick()``
method that the DroneNode calls on every main-loop iteration.

State transitions
─────────────────
  FOLLOWER  ──(election timeout)──▸  CANDIDATE
  CANDIDATE ──(majority votes)────▸  LEADER
  CANDIDATE ──(higher term seen)──▸  FOLLOWER
  LEADER    ──(higher term seen)──▸  FOLLOWER
"""

from __future__ import annotations

import logging
import random
import time

from swarmnet.comms.messenger import Messenger
from swarmnet.consensus.election import (
    handle_vote_request,
    handle_vote_response,
    start_election,
)
from swarmnet.consensus.heartbeat import (
    handle_append_entries,
    handle_append_entries_response,
    send_heartbeat,
)
from swarmnet.core.config import (
    ELECTION_TIMEOUT_MAX_MS,
    ELECTION_TIMEOUT_MIN_MS,
    HEARTBEAT_INTERVAL_MS,
)
from swarmnet.core.state import DroneState

logger = logging.getLogger(__name__)


class RaftStateMachine:
    """Drives the Raft protocol for a single drone node.

    Args:
        state:     The node's :class:`DroneState` (mutated in place).
        messenger: The node's :class:`Messenger` for sending/receiving.
        n_total:   Total number of drones in the cluster.
        seed:      Optional random seed for deterministic election timeouts.
    """

    def __init__(
        self,
        state: DroneState,
        messenger: Messenger,
        n_total: int,
        seed: int | None = None,
    ) -> None:
        self.state = state
        self.messenger = messenger
        self.n_total = n_total
        self._rng = random.Random(seed)

        # Timestamps (monotonic seconds)
        self._election_timeout = self._new_election_timeout()
        self._last_heartbeat_sent = 0.0

        # Metrics callback (set by MetricsCollector)
        self.on_election_complete = None  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tick(self, messages: list[dict] | None = None) -> None:
        """Single iteration of the Raft state machine.

        Called from the DroneNode main loop. Processes pending Raft messages
        and performs time-based actions (election timeout, heartbeat sending).
        If *messages* is omitted, the Raft machine drains the messenger itself
        for backwards-compatible standalone use.
        """
        # 1. Process all pending messages
        if messages is None:
            messages = self.messenger.drain_all(timeout_ms=1)
        for msg in messages:
            self.handle_message(msg)

        # 2. Role-specific time-based actions
        now = time.monotonic()

        if self.state.raft_state == "follower":
            self._follower_tick(now)
        elif self.state.raft_state == "candidate":
            self._candidate_tick(now)
        elif self.state.raft_state == "leader":
            self._leader_tick(now)

    def replicate_command(self, command: str) -> bool:
        """Append and replicate a command from the current leader."""
        if self.state.raft_state != "leader":
            return False

        prev_log_index = len(self.state.log)
        prev_log_term = (
            self.state.log[prev_log_index - 1]["term"]
            if prev_log_index > 0
            else 0
        )
        entry = {
            "index": prev_log_index + 1,
            "term": self.state.current_term,
            "command": command,
            "committed": False,
        }
        self.state.log.append(entry)

        if self.n_total == 1:
            self.state.commit_index = entry["index"]
            entry["committed"] = True
            return True

        msg = {
            "type": "append_entries",
            "term": self.state.current_term,
            "leader_id": self.state.drone_id,
            "prev_log_index": prev_log_index,
            "prev_log_term": prev_log_term,
            "entries": [entry],
            "leader_commit": self.state.commit_index,
        }
        sent = self.messenger.send_to_all(msg)
        logger.info(
            "[DRONE %d] Replicating command %r to %d peer(s)",
            self.state.drone_id,
            command,
            sent,
        )
        return sent > 0

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    def handle_message(self, msg: dict) -> None:
        """Route an incoming message to the appropriate handler."""
        msg_type = msg.get("type")

        if msg_type == "vote_request":
            handle_vote_request(msg, self.state, self.messenger)

        elif msg_type == "vote_response":
            won = handle_vote_response(msg, self.state, self.n_total)
            if won:
                # Immediately send heartbeats to assert authority
                send_heartbeat(self.state, self.messenger)
                self._last_heartbeat_sent = time.monotonic()
                if self.on_election_complete:
                    elapsed = (
                        time.monotonic() - self.state.last_heartbeat
                    ) * 1000
                    self.on_election_complete(
                        self.state.current_term, elapsed
                    )

        elif msg_type == "append_entries":
            handle_append_entries(msg, self.state, self.messenger)

        elif msg_type == "append_entries_response":
            handle_append_entries_response(msg, self.state)

        else:
            logger.debug(
                "[DRONE %d] Ignoring unknown message type: %s",
                self.state.drone_id,
                msg_type,
            )

    # ------------------------------------------------------------------
    # Role ticks
    # ------------------------------------------------------------------

    def _follower_tick(self, now: float) -> None:
        """Check if the election timeout has fired."""
        elapsed_ms = (now - self.state.last_heartbeat) * 1000
        if elapsed_ms >= self._election_timeout:
            logger.info(
                "[DRONE %d] Election timeout fired (%.0f ms >= %.0f ms)",
                self.state.drone_id,
                elapsed_ms,
                self._election_timeout,
            )
            start_election(self.state, self.messenger)
            self._election_timeout = self._new_election_timeout()

    def _candidate_tick(self, now: float) -> None:
        """Re-start election if the candidate timeout fires again."""
        elapsed_ms = (now - self.state.last_heartbeat) * 1000
        if elapsed_ms >= self._election_timeout:
            logger.info(
                "[DRONE %d] Candidate timeout — retrying election",
                self.state.drone_id,
            )
            start_election(self.state, self.messenger)
            self._election_timeout = self._new_election_timeout()

    def _leader_tick(self, now: float) -> None:
        """Send periodic heartbeats."""
        elapsed_ms = (now - self._last_heartbeat_sent) * 1000
        if elapsed_ms >= HEARTBEAT_INTERVAL_MS:
            send_heartbeat(self.state, self.messenger)
            self._last_heartbeat_sent = now

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _new_election_timeout(self) -> float:
        """Return a random election timeout in ms within the configured range."""
        return self._rng.uniform(
            ELECTION_TIMEOUT_MIN_MS, ELECTION_TIMEOUT_MAX_MS
        )
