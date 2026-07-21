"""
gossip_agent.py - Periodic push gossip for Phase 2 state synchronization.

The agent owns a local GossipStateTable, pushes it to a random peer fanout,
and records local convergence when all expected drones have fresh entries.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Iterable

from swarmnet.comms.messenger import Messenger
from swarmnet.core.config import GOSSIP_FANOUT, GOSSIP_INTERVAL_MS
from swarmnet.core.state import DroneState
from swarmnet.gossip.state_table import GossipStateTable
from swarmnet.metrics.collector import MetricsCollector

logger = logging.getLogger(__name__)


class GossipAgent:
    """Runs the Phase 2 gossip state synchronization loop."""

    def __init__(
        self,
        state: DroneState,
        messenger: Messenger,
        metrics: MetricsCollector | None = None,
        interval_ms: int = GOSSIP_INTERVAL_MS,
        fanout: int = GOSSIP_FANOUT,
        seed: int | None = None,
    ) -> None:
        if interval_ms <= 0:
            raise ValueError("interval_ms must be positive")
        if fanout < 0:
            raise ValueError("fanout must be non-negative")

        self.state = state
        self.messenger = messenger
        self.metrics = metrics
        self.interval_ms = interval_ms
        self.fanout = fanout
        self.state_table = GossipStateTable()
        self.state_table.upsert_local_state(state)

        self._rng = random.Random(seed)
        self._last_gossip_sent = 0.0
        self._round_start_timestamp = time.time()
        self._rounds_since_start = 0
        self.last_convergence_rounds: int | None = None

    @property
    def expected_ids(self) -> set[int]:
        """All drone IDs expected in the local convergence check."""
        return {self.state.drone_id, *self.state.peers}

    def start_convergence_round(self) -> None:
        """Reset convergence measurement for a fresh gossip window."""
        self._round_start_timestamp = time.time()
        self._rounds_since_start = 0

    def tick(
        self,
        incoming_messages: Iterable[dict] | None = None,
        now: float | None = None,
    ) -> None:
        """Process inbound gossip and send on the configured interval."""
        monotonic_now = time.monotonic() if now is None else now

        self.state_table.upsert_local_state(self.state)
        for msg in incoming_messages or []:
            self.handle_message(msg)

        self._maybe_record_convergence()

        elapsed_ms = (monotonic_now - self._last_gossip_sent) * 1000
        if elapsed_ms >= self.interval_ms:
            self.gossip_once()
            self._last_gossip_sent = monotonic_now

    def handle_message(self, msg: dict) -> int:
        """Merge one incoming gossip message and return updated entries."""
        if msg.get("type") != "gossip":
            return 0

        state_table = msg.get("state_table")
        if not isinstance(state_table, dict):
            logger.debug(
                "[DRONE %d] Ignoring malformed gossip message from %s",
                self.state.drone_id,
                msg.get("sender_id"),
            )
            return 0

        updated = self.state_table.merge(state_table)
        if updated:
            logger.debug(
                "[DRONE %d] Gossip merged %d updates from drone %s",
                self.state.drone_id,
                updated,
                msg.get("sender_id"),
            )
        return updated

    def gossip_once(self) -> int:
        """Push the current state table to a random peer fanout."""
        self.state_table.upsert_local_state(self.state)
        peers = self.select_peers()
        if not peers:
            self._rounds_since_start += 1
            return 0

        msg = {
            "type": "gossip",
            "sender_id": self.state.drone_id,
            "state_table": self.state_table.to_dict(),
        }

        sent = 0
        for peer_id in peers:
            if self.messenger.send_to(peer_id, msg):
                sent += 1

        self._rounds_since_start += 1
        logger.debug(
            "[DRONE %d] Gossip pushed to %d/%d peers",
            self.state.drone_id,
            sent,
            len(peers),
        )
        return sent

    def select_peers(self) -> list[int]:
        """Choose up to fanout random peers without replacement."""
        if self.fanout == 0 or not self.state.peers:
            return []
        sample_size = min(self.fanout, len(self.state.peers))
        return self._rng.sample(self.state.peers, sample_size)

    def _maybe_record_convergence(self) -> None:
        """Record a gossip metric when this node has a fresh full table."""
        if not self.state_table.has_converged(
            self.expected_ids,
            self._round_start_timestamp,
        ):
            return

        rounds = max(1, self._rounds_since_start)
        self.last_convergence_rounds = rounds
        if self.metrics is not None:
            self.metrics.record_gossip(rounds)

        logger.info(
            "[DRONE %d] Gossip converged locally in %d round(s)",
            self.state.drone_id,
            rounds,
        )
        self.start_convergence_round()
