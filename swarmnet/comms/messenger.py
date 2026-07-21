"""
messenger.py — ZeroMQ socket setup, send/receive wrappers.

Each DroneNode owns one Messenger instance that manages:
  - A PULL socket for receiving unicast RPCs (vote requests, heartbeats,
    append-entries, gossip pushes).
  - PUSH sockets to every peer for sending unicast messages.
  - A PUB socket for broadcasting state to the visualizer / dashboard.

Port scheme (from TRD §5):
  PULL:  BASE_PORT + drone_id
  PUB:   BASE_PORT + 100 + drone_id
"""

from __future__ import annotations

import logging
from typing import Any

import zmq

from swarmnet.comms.fault_sim import FaultSimulator
from swarmnet.comms.serializer import decode, encode
from swarmnet.core.config import BASE_PORT

logger = logging.getLogger(__name__)


class Messenger:
    """Manages all ZeroMQ sockets for a single drone node.

    Args:
        drone_id:    This node's unique identifier.
        peer_ids:    List of all other drone IDs in the cluster.
        fault_sim:   Optional :class:`FaultSimulator` for packet-loss testing.
    """

    def __init__(
        self,
        drone_id: int,
        peer_ids: list[int],
        fault_sim: FaultSimulator | None = None,
    ) -> None:
        self.drone_id = drone_id
        self.peer_ids = peer_ids
        self.fault_sim = fault_sim or FaultSimulator(0.0)
        self.sent_count = 0
        self.message_counts: dict[str, int] = {}

        self._ctx = zmq.Context()

        # ---- PULL socket (receive from peers) ----------------------------
        self._pull = self._ctx.socket(zmq.PULL)
        pull_port = BASE_PORT + drone_id
        self._pull.bind(f"tcp://127.0.0.1:{pull_port}")
        logger.info("[DRONE %d] PULL bound on port %d", drone_id, pull_port)

        # ---- PUB socket (broadcast state) --------------------------------
        self._pub = self._ctx.socket(zmq.PUB)
        pub_port = BASE_PORT + 100 + drone_id
        self._pub.bind(f"tcp://127.0.0.1:{pub_port}")
        logger.info("[DRONE %d] PUB  bound on port %d", drone_id, pub_port)

        # ---- PUSH sockets (one per peer) ---------------------------------
        self._push: dict[int, zmq.Socket] = {}
        for pid in peer_ids:
            sock = self._ctx.socket(zmq.PUSH)
            sock.setsockopt(zmq.SNDHWM, 100)
            sock.setsockopt(zmq.LINGER, 0)
            peer_pull_port = BASE_PORT + pid
            sock.connect(f"tcp://127.0.0.1:{peer_pull_port}")
            self._push[pid] = sock
        logger.info(
            "[DRONE %d] PUSH connected to %d peers", drone_id, len(peer_ids)
        )

        # ---- Poller for non-blocking receive -----------------------------
        self._poller = zmq.Poller()
        self._poller.register(self._pull, zmq.POLLIN)

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------

    def send_to(self, peer_id: int, msg: dict[str, Any]) -> bool:
        """Send a message to a specific peer.

        Returns ``True`` if the message was actually sent (not dropped by
        the fault simulator).
        """
        if self.fault_sim.should_drop():
            return False
        try:
            self._push[peer_id].send(encode(msg), zmq.NOBLOCK)
            self._record_sent(msg)
            return True
        except zmq.ZMQError as exc:
            logger.warning(
                "[DRONE %d] send_to(%d) failed: %s", self.drone_id, peer_id, exc
            )
            return False

    def broadcast(self, msg: dict[str, Any]) -> None:
        """Publish a message on the PUB socket (for visualizer/dashboard)."""
        try:
            self._pub.send(encode(msg), zmq.NOBLOCK)
            self._record_sent(msg)
        except zmq.ZMQError as exc:
            logger.warning("[DRONE %d] broadcast failed: %s", self.drone_id, exc)

    def send_to_all(self, msg: dict[str, Any]) -> int:
        """Send a message to every peer.  Returns the count of successful sends."""
        sent = 0
        for pid in self.peer_ids:
            if self.send_to(pid, msg):
                sent += 1
        return sent

    def _record_sent(self, msg: dict[str, Any]) -> None:
        """Track successful outbound messages for dashboard diagnostics."""
        self.sent_count += 1
        message_type = str(msg.get("type", "unknown"))
        self.message_counts[message_type] = self.message_counts.get(message_type, 0) + 1

    # ------------------------------------------------------------------
    # Receive helpers
    # ------------------------------------------------------------------

    def recv_nowait(self, timeout_ms: int = 0) -> dict[str, Any] | None:
        """Non-blocking receive on the PULL socket.

        Args:
            timeout_ms: Maximum time to wait for a message (0 = return
                        immediately if nothing is available).

        Returns:
            Decoded message dict, or ``None`` if no message is ready.
        """
        socks = dict(self._poller.poll(timeout_ms))
        if self._pull in socks:
            raw = self._pull.recv(zmq.NOBLOCK)
            return decode(raw)
        return None

    def drain_all(self, timeout_ms: int = 0) -> list[dict[str, Any]]:
        """Receive all pending messages (drains the PULL buffer).

        Returns:
            List of decoded message dicts (possibly empty).
        """
        messages: list[dict[str, Any]] = []
        # First poll with the caller's timeout, then drain remaining
        while True:
            msg = self.recv_nowait(timeout_ms if not messages else 0)
            if msg is None:
                break
            messages.append(msg)
        return messages

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close all sockets and terminate the ZeroMQ context."""
        for sock in self._push.values():
            sock.close(linger=0)
        self._pull.close(linger=0)
        self._pub.close(linger=0)
        self._ctx.term()
        logger.info("[DRONE %d] Messenger closed", self.drone_id)
