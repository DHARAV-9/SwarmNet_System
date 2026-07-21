"""
test_gossip.py - Unit tests for Phase 2 gossip state synchronization.
"""

from __future__ import annotations

import csv
import time

from swarmnet.core.state import DroneState
from swarmnet.gossip.gossip_agent import GossipAgent
from swarmnet.gossip.state_table import GossipStateTable, StateTableEntry
from swarmnet.metrics.collector import MetricsCollector


class FakeMessenger:
    """Minimal messenger test double for gossip sends."""

    def __init__(self, drone_id: int, peer_ids: list[int]) -> None:
        self.drone_id = drone_id
        self.peer_ids = peer_ids
        self.sent: list[tuple[int, dict]] = []

    def send_to(self, peer_id: int, msg: dict) -> bool:
        self.sent.append((peer_id, msg))
        return True


def make_state(drone_id: int = 0, n: int = 3) -> DroneState:
    """Build a DroneState with deterministic peers."""
    return DroneState(
        drone_id=drone_id,
        x=100.0 + drone_id,
        y=200.0 + drone_id,
        vx=1.0,
        vy=-1.0,
        peers=[i for i in range(n) if i != drone_id],
    )


def make_entry(drone_id: int, timestamp: float, x: float = 0.0) -> StateTableEntry:
    """Build a test table entry."""
    return StateTableEntry(
        drone_id=drone_id,
        x=x,
        y=0.0,
        vx=0.0,
        vy=0.0,
        battery=100.0,
        task=None,
        raft_state="follower",
        term=1,
        timestamp=timestamp,
    )


class TestGossipStateTable:
    def test_merge_keeps_newest_timestamp(self):
        table = GossipStateTable([make_entry(1, timestamp=10.0, x=10.0)])

        updated = table.merge(
            {"1": make_entry(1, timestamp=9.0, x=99.0).to_dict()}
        )
        assert updated == 0
        assert table.get(1).x == 10.0

        updated = table.merge(
            {"1": make_entry(1, timestamp=11.0, x=42.0).to_dict()}
        )
        assert updated == 1
        assert table.get(1).x == 42.0

    def test_local_state_serializes_to_trd_shape(self):
        state = make_state(0)
        table = GossipStateTable()
        table.upsert_local_state(state, timestamp=123.0)

        payload = table.to_dict()
        assert set(payload) == {"0"}
        assert payload["0"]["drone_id"] == 0
        assert payload["0"]["term"] == state.current_term
        assert payload["0"]["timestamp"] == 123.0

    def test_convergence_requires_all_fresh_entries(self):
        table = GossipStateTable(
            [
                make_entry(0, timestamp=20.0),
                make_entry(1, timestamp=20.0),
                make_entry(2, timestamp=5.0),
            ]
        )

        assert not table.has_converged({0, 1, 2}, since_timestamp=10.0)
        table.upsert(make_entry(2, timestamp=20.0))
        assert table.has_converged({0, 1, 2}, since_timestamp=10.0)


class TestGossipAgent:
    def test_gossip_once_sends_state_table_to_random_fanout(self):
        state = make_state(0, n=5)
        messenger = FakeMessenger(0, state.peers)
        agent = GossipAgent(state, messenger, interval_ms=200, fanout=2, seed=7)

        sent = agent.gossip_once()

        assert sent == 2
        assert len(messenger.sent) == 2
        for peer_id, msg in messenger.sent:
            assert peer_id in state.peers
            assert msg["type"] == "gossip"
            assert msg["sender_id"] == 0
            assert "0" in msg["state_table"]

    def test_handle_message_merges_incoming_state_table(self):
        state = make_state(0, n=3)
        messenger = FakeMessenger(0, state.peers)
        agent = GossipAgent(state, messenger, interval_ms=200, fanout=2, seed=1)

        msg = {
            "type": "gossip",
            "sender_id": 1,
            "state_table": {
                "1": make_entry(1, timestamp=time.time() + 1.0).to_dict()
            },
        }

        updated = agent.handle_message(msg)

        assert updated == 1
        assert 1 in agent.state_table

    def test_tick_records_gossip_convergence_metric(self):
        state = make_state(0, n=3)
        messenger = FakeMessenger(0, state.peers)
        metrics = MetricsCollector(swarm_size=3)
        agent = GossipAgent(
            state,
            messenger,
            metrics,
            interval_ms=60_000,
            fanout=2,
            seed=1,
        )
        fresh_timestamp = time.time() + 1.0
        incoming = [
            {
                "type": "gossip",
                "sender_id": 1,
                "state_table": {
                    "1": make_entry(1, fresh_timestamp).to_dict(),
                    "2": make_entry(2, fresh_timestamp).to_dict(),
                },
            }
        ]

        agent.tick(incoming_messages=incoming, now=1.0)

        records = metrics.get_gossip_records()
        assert len(records) == 1
        assert records[0].value == 1.0
        assert agent.last_convergence_rounds == 1


class TestMetricsExport:
    def test_metrics_collector_exports_csv(self, tmp_path):
        metrics = MetricsCollector(swarm_size=5)
        metrics.record_gossip(rounds=3)

        output_path = metrics.export_csv(tmp_path / "metrics.csv")

        with output_path.open(newline="", encoding="utf-8") as csv_file:
            rows = list(csv.DictReader(csv_file))

        assert rows[0]["event_type"] == "gossip"
        assert rows[0]["value"] == "3.000000"
        assert rows[0]["swarm_size"] == "5"
        assert rows[0]["packet_loss"] == "0.000000"
