"""
collector.py - Metrics collector for SwarmNet.

Logs election, gossip, and formation events with timestamps. Phase 2 adds CSV
export so gossip convergence data can be used in reports and benchmarks.
"""

from __future__ import annotations

import csv
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from swarmnet.core.config import METRICS_DIR

logger = logging.getLogger(__name__)


@dataclass
class MetricsRecord:
    """A single metrics event."""

    event_type: str  # "election" | "gossip" | "formation" | "message_rate"
    timestamp: float
    value: float  # election_ms | convergence_rounds | avg_error | messages/sec
    swarm_size: int
    drone_id: int | None = None
    packet_loss: float = 0.0

    def to_row(self) -> dict[str, str]:
        """Return a CSV-ready row."""
        return {
            "event_type": self.event_type,
            "timestamp": f"{self.timestamp:.6f}",
            "value": f"{self.value:.6f}",
            "swarm_size": str(self.swarm_size),
            "drone_id": "" if self.drone_id is None else str(self.drone_id),
            "packet_loss": f"{self.packet_loss:.6f}",
        }


class MetricsCollector:
    """Collects and stores metrics events in memory.

    Attributes:
        records:  List of all recorded :class:`MetricsRecord` objects.
    """

    def __init__(
        self,
        swarm_size: int,
        drone_id: int | None = None,
        packet_loss: float = 0.0,
    ) -> None:
        self.swarm_size = swarm_size
        self.drone_id = drone_id
        self.packet_loss = packet_loss
        self.records: list[MetricsRecord] = []

    def _record(self, event_type: str, value: float) -> MetricsRecord:
        """Create and retain one metric record with run metadata."""
        record = MetricsRecord(
            event_type=event_type,
            timestamp=time.time(),
            value=value,
            swarm_size=self.swarm_size,
            drone_id=self.drone_id,
            packet_loss=self.packet_loss,
        )
        self.records.append(record)
        return record

    def record_election(self, term: int, time_ms: float) -> None:
        """Log an election completion event.

        Args:
            term:    The Raft term number of the completed election.
            time_ms: Time in milliseconds the election took.
        """
        self._record("election", time_ms)
        logger.info(
            "[METRICS] Election completed: term=%d, time=%.1f ms",
            term,
            time_ms,
        )

    def record_gossip(self, rounds: int) -> None:
        """Log a gossip convergence event."""
        self._record("gossip", float(rounds))
        logger.info("[METRICS] Gossip converged in %d round(s)", rounds)

    def record_formation(self, avg_error: float) -> None:
        """Log a formation error event (stub for Phase 3)."""
        self._record("formation", avg_error)

    def record_message_rate(self, messages_per_second: float) -> None:
        """Log aggregate outgoing message throughput for this drone."""
        self._record("message_rate", messages_per_second)

    def get_election_records(self) -> list[MetricsRecord]:
        """Return all election-type records."""
        return [r for r in self.records if r.event_type == "election"]

    def get_gossip_records(self) -> list[MetricsRecord]:
        """Return all gossip-type records."""
        return [r for r in self.records if r.event_type == "gossip"]

    def export_csv(self, path: str | Path | None = None) -> Path:
        """Write all collected metrics to a CSV file and return the path."""
        output_path = Path(path) if path is not None else Path(METRICS_DIR)
        if output_path.suffix.lower() != ".csv":
            output_path = output_path / "swarmnet_metrics.csv"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(
                csv_file,
                fieldnames=[
                    "event_type",
                    "timestamp",
                    "value",
                    "swarm_size",
                    "drone_id",
                    "packet_loss",
                ],
            )
            writer.writeheader()
            for record in self.records:
                writer.writerow(record.to_row())

        logger.info(
            "[METRICS] Exported %d records to %s",
            len(self.records),
            output_path,
        )
        return output_path
