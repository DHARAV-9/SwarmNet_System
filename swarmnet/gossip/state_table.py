"""
state_table.py - Eventually consistent world-state table for gossip.

Each drone keeps one table keyed by drone ID. Incoming gossip messages are
merged using last-writer-wins timestamps, matching the Phase 2 TRD merge rule.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from swarmnet.core.state import DroneState


@dataclass(frozen=True)
class StateTableEntry:
    """Serializable state snapshot for one drone."""

    drone_id: int
    x: float
    y: float
    vx: float
    vy: float
    battery: float
    task: str | None
    raft_state: str
    term: int
    timestamp: float

    @classmethod
    def from_drone_state(
        cls,
        state: DroneState,
        timestamp: float | None = None,
    ) -> StateTableEntry:
        """Build a gossip table entry from live drone state."""
        return cls(
            drone_id=state.drone_id,
            x=float(state.x),
            y=float(state.y),
            vx=float(state.vx),
            vy=float(state.vy),
            battery=float(state.battery),
            task=state.task,
            raft_state=state.raft_state,
            term=int(state.current_term),
            timestamp=time.time() if timestamp is None else float(timestamp),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StateTableEntry:
        """Deserialize an entry received over JSON."""
        return cls(
            drone_id=int(data["drone_id"]),
            x=float(data["x"]),
            y=float(data["y"]),
            vx=float(data["vx"]),
            vy=float(data["vy"]),
            battery=float(data["battery"]),
            task=data.get("task"),
            raft_state=str(data["raft_state"]),
            term=int(data["term"]),
            timestamp=float(data["timestamp"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the TRD gossip message schema."""
        return {
            "drone_id": self.drone_id,
            "x": self.x,
            "y": self.y,
            "vx": self.vx,
            "vy": self.vy,
            "battery": self.battery,
            "task": self.task,
            "raft_state": self.raft_state,
            "term": self.term,
            "timestamp": self.timestamp,
        }


class GossipStateTable:
    """Last-writer-wins table of known drone states."""

    def __init__(self, entries: Iterable[StateTableEntry] | None = None) -> None:
        self.entries: dict[int, StateTableEntry] = {}
        for entry in entries or []:
            self.upsert(entry)

    def __len__(self) -> int:
        return len(self.entries)

    def __contains__(self, drone_id: int) -> bool:
        return drone_id in self.entries

    def get(self, drone_id: int) -> StateTableEntry | None:
        """Return the latest entry for *drone_id*, if known."""
        return self.entries.get(drone_id)

    def upsert(self, entry: StateTableEntry) -> bool:
        """Insert *entry* if it is newer than the current table value."""
        current = self.entries.get(entry.drone_id)
        if current is not None and current.timestamp >= entry.timestamp:
            return False
        self.entries[entry.drone_id] = entry
        return True

    def upsert_local_state(
        self,
        state: DroneState,
        timestamp: float | None = None,
    ) -> bool:
        """Refresh the table entry for this node."""
        return self.upsert(StateTableEntry.from_drone_state(state, timestamp))

    def merge(
        self,
        incoming: Mapping[int | str, StateTableEntry | Mapping[str, Any]],
    ) -> int:
        """Merge an incoming gossip table and return the update count."""
        updated = 0
        for raw_entry in incoming.values():
            entry = (
                raw_entry
                if isinstance(raw_entry, StateTableEntry)
                else StateTableEntry.from_dict(raw_entry)
            )
            if self.upsert(entry):
                updated += 1
        return updated

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Serialize the table using string keys for JSON transport."""
        return {
            str(drone_id): self.entries[drone_id].to_dict()
            for drone_id in sorted(self.entries)
        }

    def known_ids(self) -> set[int]:
        """Return all drone IDs currently known to this table."""
        return set(self.entries)

    def has_converged(
        self,
        expected_ids: Iterable[int],
        since_timestamp: float,
    ) -> bool:
        """Return True when every expected ID has a fresh entry."""
        for drone_id in expected_ids:
            entry = self.entries.get(drone_id)
            if entry is None or entry.timestamp < since_timestamp:
                return False
        return True

    def missing_ids(
        self,
        expected_ids: Iterable[int],
        since_timestamp: float,
    ) -> set[int]:
        """Return IDs with no fresh entry since *since_timestamp*."""
        missing: set[int] = set()
        for drone_id in expected_ids:
            entry = self.entries.get(drone_id)
            if entry is None or entry.timestamp < since_timestamp:
                missing.add(drone_id)
        return missing
