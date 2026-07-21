"""Tests for the Phase 4 Flask dashboard API."""

from __future__ import annotations

import csv
from pathlib import Path

from swarmnet.viz.dashboard import create_app


class FakeMonitor:
    """Dashboard monitor double that records requested controls."""

    def __init__(self) -> None:
        self.n_total = 2
        self.controls: list[tuple[list[int], str, dict]] = []

    def status(self) -> dict:
        return {
            "leader_id": 0,
            "nodes": [
                {"drone_id": 0, "alive": True, "status": "leader"},
                {"drone_id": 1, "alive": True, "status": "follower"},
            ],
            "tasks": [],
        }

    def metrics(self) -> dict:
        return {
            "gossip_rounds": 2,
            "formation_error": 4.5,
            "message_rate": 12.0,
            "packet_loss": 0.1,
        }

    def send_control(self, drone_ids: list[int], command: str, **values: object) -> int:
        self.controls.append((drone_ids, command, values))
        return len(drone_ids)


def make_client(tmp_path: Path):
    monitor = FakeMonitor()
    app = create_app(monitor, tmp_path)
    app.config["TESTING"] = True
    return app.test_client(), monitor


def test_dashboard_status_and_metrics_endpoints(tmp_path):
    client, _ = make_client(tmp_path)

    assert client.get("/api/status").get_json()["leader_id"] == 0
    assert client.get("/api/metrics").get_json()["gossip_rounds"] == 2


def test_dashboard_fault_controls_validate_and_send(tmp_path):
    client, monitor = make_client(tmp_path)

    response = client.post("/api/kill/1")
    assert response.status_code == 200
    assert monitor.controls[-1] == ([1], "kill", {})

    response = client.post("/api/packet_loss", json={"rate": 0.3})
    assert response.status_code == 200
    assert monitor.controls[-1] == ([0, 1], "set_packet_loss", {"rate": 0.3})

    assert client.post("/api/packet_loss", json={"rate": 1.2}).status_code == 400
    assert client.post("/api/kill/3").status_code == 404


def test_dashboard_metric_export_downloads_combined_csv(tmp_path):
    source = tmp_path / "drone_0_metrics.csv"
    with source.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["event_type", "timestamp", "value", "swarm_size"],
        )
        writer.writeheader()
        writer.writerow(
            {"event_type": "gossip", "timestamp": "1", "value": "2", "swarm_size": "5"}
        )

    client, _ = make_client(tmp_path)
    response = client.get("/api/metrics/export")

    assert response.status_code == 200
    assert b"event_type,timestamp,value,swarm_size,drone_id,packet_loss" in response.data


def test_dashboard_announces_task_through_current_leader(tmp_path):
    client, monitor = make_client(tmp_path)

    response = client.post(
        "/api/tasks",
        json={"task_id": "scan-a", "description": "Scan A", "x": 120, "y": 240},
    )

    assert response.status_code == 202
    assert monitor.controls[-1] == (
        [0],
        "announce_task",
        {
            "task_id": "scan-a",
            "description": "Scan A",
            "x": 120.0,
            "y": 240.0,
            "deadline_seconds": 60.0,
        },
    )
