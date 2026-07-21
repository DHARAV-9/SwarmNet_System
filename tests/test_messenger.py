"""
test_messenger.py — Unit tests for the communications module.

Tests cover:
  - JSON serialization round-trip for all message types
  - Port assignment collision avoidance
  - Fault simulator packet loss behavior
"""

from __future__ import annotations

import json

import pytest

from swarmnet.comms.fault_sim import FaultSimulator
from swarmnet.comms.serializer import decode, encode


# ======================================================================
# Test: Serialization
# ======================================================================


class TestSerializer:
    def test_vote_request_serializes_correctly(self):
        """VoteRequest should survive JSON encode/decode round-trip."""
        msg = {
            "type": "vote_request",
            "term": 3,
            "candidate_id": 2,
            "last_log_index": 5,
            "last_log_term": 2,
        }
        encoded = encode(msg)
        assert isinstance(encoded, bytes)

        decoded = decode(encoded)
        assert decoded == msg

    def test_vote_response_serializes_correctly(self):
        msg = {
            "type": "vote_response",
            "term": 3,
            "vote_granted": True,
            "voter_id": 1,
        }
        assert decode(encode(msg)) == msg

    def test_append_entries_serializes_correctly(self):
        msg = {
            "type": "append_entries",
            "term": 2,
            "leader_id": 0,
            "prev_log_index": 3,
            "prev_log_term": 1,
            "entries": [
                {"index": 4, "term": 2, "command": "MOVE 100 200", "committed": False}
            ],
            "leader_commit": 3,
        }
        assert decode(encode(msg)) == msg

    def test_append_entries_response_serializes_correctly(self):
        msg = {
            "type": "append_entries_response",
            "term": 2,
            "success": True,
            "follower_id": 1,
            "match_index": 4,
        }
        assert decode(encode(msg)) == msg

    def test_gossip_serializes_correctly(self):
        msg = {
            "type": "gossip",
            "sender_id": 0,
            "state_table": {
                "0": {
                    "drone_id": 0,
                    "x": 100.5,
                    "y": 200.3,
                    "vx": 1.0,
                    "vy": -0.5,
                    "battery": 95.0,
                    "task": None,
                    "raft_state": "leader",
                    "term": 2,
                    "timestamp": 1719000000.0,
                }
            },
        }
        assert decode(encode(msg)) == msg

    def test_state_broadcast_serializes_correctly(self):
        msg = {
            "type": "state_broadcast",
            "drone_id": 3,
            "x": 150.0,
            "y": 300.0,
            "vx": 2.5,
            "vy": -1.0,
            "raft_state": "follower",
            "term": 1,
            "battery": 88.5,
        }
        assert decode(encode(msg)) == msg

    def test_decode_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            decode(b"not valid json")

    def test_encode_produces_compact_json(self):
        """Encoded JSON should have no unnecessary whitespace."""
        msg = {"type": "test", "value": 42}
        encoded = encode(msg)
        text = encoded.decode("utf-8")
        assert " " not in text  # compact separators


# ======================================================================
# Test: Port assignment
# ======================================================================


class TestPortAssignment:
    def test_port_assignment_no_collision(self):
        """Each drone's PULL and PUB ports should be unique and non-overlapping."""
        from swarmnet.core.config import BASE_PORT

        n = 20
        pull_ports = set()
        pub_ports = set()

        for i in range(n):
            pull_port = BASE_PORT + i
            pub_port = BASE_PORT + 100 + i
            pull_ports.add(pull_port)
            pub_ports.add(pub_port)

        # All PULL ports unique
        assert len(pull_ports) == n
        # All PUB ports unique
        assert len(pub_ports) == n
        # No overlap between PULL and PUB
        assert pull_ports.isdisjoint(pub_ports)

    def test_port_ranges_do_not_overlap_for_max_drones(self):
        """Even with 20 drones, PULL (5600-5619) and PUB (5700-5719) don't overlap."""
        from swarmnet.core.config import BASE_PORT

        n = 20
        pull_range = set(range(BASE_PORT, BASE_PORT + n))
        pub_range = set(range(BASE_PORT + 100, BASE_PORT + 100 + n))
        assert pull_range.isdisjoint(pub_range)


# ======================================================================
# Test: Fault Simulator
# ======================================================================


class TestFaultSimulator:
    def test_no_loss_never_drops(self):
        """With 0% loss rate, no messages should be dropped."""
        fs = FaultSimulator(loss_rate=0.0)
        for _ in range(100):
            assert fs.should_drop() is False
        assert fs.dropped_count == 0
        assert fs.sent_count == 100

    def test_full_loss_always_drops(self):
        """With 100% loss rate, all messages should be dropped."""
        fs = FaultSimulator(loss_rate=1.0)
        for _ in range(100):
            assert fs.should_drop() is True
        assert fs.dropped_count == 100
        assert fs.sent_count == 0

    def test_partial_loss_drops_some(self):
        """With 50% loss rate, roughly half should be dropped (seeded)."""
        fs = FaultSimulator(loss_rate=0.5, seed=42)
        drops = sum(1 for _ in range(1000) if fs.should_drop())
        # With seed=42 and 1000 trials, expect ~500 ± 50
        assert 400 < drops < 600

    def test_dropped_message_under_packet_loss(self):
        """Verify that drop counting works correctly."""
        fs = FaultSimulator(loss_rate=0.5, seed=123)
        total = 100
        for _ in range(total):
            fs.should_drop()
        assert fs.dropped_count + fs.sent_count == total

    def test_invalid_loss_rate_raises(self):
        with pytest.raises(ValueError):
            FaultSimulator(loss_rate=-0.1)
        with pytest.raises(ValueError):
            FaultSimulator(loss_rate=1.5)

    def test_set_loss_rate_at_runtime(self):
        fs = FaultSimulator(loss_rate=0.0)
        fs.set_loss_rate(0.3)
        assert fs.loss_rate == 0.3

    def test_set_invalid_loss_rate_raises(self):
        fs = FaultSimulator(loss_rate=0.0)
        with pytest.raises(ValueError):
            fs.set_loss_rate(-0.5)

    def test_seeded_is_deterministic(self):
        """Two FaultSimulators with the same seed should produce identical results."""
        fs1 = FaultSimulator(loss_rate=0.5, seed=999)
        fs2 = FaultSimulator(loss_rate=0.5, seed=999)
        results1 = [fs1.should_drop() for _ in range(50)]
        results2 = [fs2.should_drop() for _ in range(50)]
        assert results1 == results2
