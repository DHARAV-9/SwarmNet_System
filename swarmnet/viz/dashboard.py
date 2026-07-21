"""Flask dashboard and ZeroMQ monitor for SwarmNet Phase 4."""

from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path
from typing import Any

import zmq
from flask import Flask, jsonify, render_template, request, send_file

from swarmnet.comms.serializer import decode, encode
from swarmnet.core.config import BASE_PORT, DASHBOARD_PORT, METRICS_DIR
from swarmnet.metrics.exporter import export_combined_metrics

STALE_AFTER_SECONDS = 3.0


class DashboardMonitor:
    """Maintain latest drone broadcasts and send dashboard controls."""

    def __init__(self, n_total: int, base_port: int = BASE_PORT) -> None:
        self.n_total = n_total
        self.base_port = base_port
        self._states: dict[int, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._context = zmq.Context()
        self._poller = zmq.Poller()
        self._subscribers: list[zmq.Socket] = []
        self._push: dict[int, zmq.Socket] = {}
        self._connect_sockets()

    def _connect_sockets(self) -> None:
        """Connect dashboard sockets to each drone's public/control ports."""
        for drone_id in range(self.n_total):
            subscriber = self._context.socket(zmq.SUB)
            subscriber.setsockopt(zmq.SUBSCRIBE, b"")
            subscriber.setsockopt(zmq.LINGER, 0)
            subscriber.connect(f"tcp://127.0.0.1:{self.base_port + 100 + drone_id}")
            self._poller.register(subscriber, zmq.POLLIN)
            self._subscribers.append(subscriber)

            sender = self._context.socket(zmq.PUSH)
            sender.setsockopt(zmq.SNDHWM, 100)
            sender.setsockopt(zmq.LINGER, 0)
            sender.connect(f"tcp://127.0.0.1:{self.base_port + drone_id}")
            self._push[drone_id] = sender

    def start(self) -> None:
        """Start receiving state broadcasts in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()

    def _receive_loop(self) -> None:
        while self._running:
            for socket in dict(self._poller.poll(100)).keys():
                try:
                    message = decode(socket.recv(zmq.NOBLOCK))
                except (ValueError, zmq.ZMQError):
                    continue
                if message.get("type") == "state_broadcast":
                    self.update_state(message)

    def update_state(self, message: dict[str, Any]) -> None:
        """Record one drone state message; exposed for deterministic tests."""
        drone_id = int(message["drone_id"])
        snapshot = dict(message)
        snapshot["last_seen"] = time.time()
        with self._lock:
            self._states[drone_id] = snapshot

    def status(self) -> dict[str, Any]:
        """Return the current normalized dashboard status payload."""
        now = time.time()
        with self._lock:
            snapshots = {drone_id: dict(state) for drone_id, state in self._states.items()}

        nodes: list[dict[str, Any]] = []
        leader_id: int | None = None
        tasks: list[dict[str, Any]] = []
        for drone_id in range(self.n_total):
            snapshot = snapshots.get(drone_id)
            if snapshot is None:
                nodes.append({"drone_id": drone_id, "alive": False, "status": "dead"})
                continue
            alive = now - float(snapshot["last_seen"]) <= STALE_AFTER_SECONDS
            snapshot["alive"] = alive
            snapshot["status"] = snapshot.get("raft_state", "unknown") if alive else "dead"
            nodes.append(snapshot)
            if alive and snapshot.get("raft_state") == "leader":
                leader_id = drone_id
                raw_tasks = snapshot.get("tasks", [])
                if isinstance(raw_tasks, list):
                    tasks = raw_tasks

        return {
            "leader_id": leader_id,
            "nodes": nodes,
            "tasks": tasks,
            "updated_at": now,
        }

    def metrics(self) -> dict[str, Any]:
        """Return aggregate latest metrics calculated from node diagnostics."""
        status = self.status()
        diagnostics = [
            node.get("diagnostics", {})
            for node in status["nodes"]
            if node.get("alive")
        ]
        if not diagnostics:
            return {
                "gossip_rounds": 0,
                "formation_error": 0.0,
                "message_rate": 0.0,
                "packet_loss": 0.0,
            }
        return {
            "gossip_rounds": max(int(item.get("gossip_rounds", 0)) for item in diagnostics),
            "formation_error": sum(float(item.get("formation_error", 0.0)) for item in diagnostics) / len(diagnostics),
            "message_rate": sum(float(item.get("message_rate", 0.0)) for item in diagnostics),
            "packet_loss": max(float(item.get("packet_loss", 0.0)) for item in diagnostics),
        }

    def send_control(self, drone_ids: list[int], command: str, **values: Any) -> int:
        """Send one control command to selected drone nodes."""
        payload = encode({"type": "control", "command": command, **values})
        sent = 0
        for drone_id in drone_ids:
            sender = self._push.get(drone_id)
            if sender is None:
                continue
            try:
                sender.send(payload, zmq.NOBLOCK)
                sent += 1
            except zmq.ZMQError:
                continue
        return sent

    def close(self) -> None:
        """Stop monitoring and release ZeroMQ resources."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        for subscriber in self._subscribers:
            subscriber.close(linger=0)
        for sender in self._push.values():
            sender.close(linger=0)
        self._context.term()


def create_app(
    monitor: DashboardMonitor,
    metrics_dir: str | Path = METRICS_DIR,
) -> Flask:
    """Build the Flask application around a running dashboard monitor."""
    app = Flask(__name__)
    app.config["MONITOR"] = monitor
    app.config["METRICS_DIR"] = Path(metrics_dir)

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/api/status")
    def api_status():
        return jsonify(monitor.status())

    @app.get("/api/metrics")
    def api_metrics():
        return jsonify(monitor.metrics())

    @app.post("/api/kill/<int:drone_id>")
    def api_kill(drone_id: int):
        if drone_id < 0 or drone_id >= monitor.n_total:
            return jsonify({"error": "unknown drone"}), 404
        sent = monitor.send_control([drone_id], "kill")
        return jsonify({"ok": sent == 1, "drone_id": drone_id})

    @app.post("/api/packet_loss")
    def api_packet_loss():
        body = request.get_json(silent=True) or {}
        try:
            rate = float(body["rate"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "rate must be a number between 0 and 1"}), 400
        if not 0.0 <= rate <= 1.0:
            return jsonify({"error": "rate must be between 0 and 1"}), 400
        sent = monitor.send_control(list(range(monitor.n_total)), "set_packet_loss", rate=rate)
        return jsonify({"ok": sent > 0, "rate": rate, "nodes_updated": sent})

    @app.get("/api/tasks")
    def api_tasks():
        return jsonify({"tasks": monitor.status().get("tasks", [])})

    @app.post("/api/tasks")
    def api_create_task():
        body = request.get_json(silent=True) or {}
        task_id = str(body.get("task_id", "")).strip()
        if not task_id:
            return jsonify({"error": "task_id is required"}), 400
        try:
            x = float(body["x"])
            y = float(body["y"])
            deadline_seconds = float(body.get("deadline_seconds", 60.0))
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "x, y, and deadline_seconds must be numbers"}), 400
        if deadline_seconds <= 0:
            return jsonify({"error": "deadline_seconds must be positive"}), 400
        leader_id = monitor.status().get("leader_id")
        if leader_id is None:
            return jsonify({"error": "no elected leader"}), 409
        sent = monitor.send_control(
            [int(leader_id)],
            "announce_task",
            task_id=task_id,
            description=str(body.get("description", task_id)),
            x=x,
            y=y,
            deadline_seconds=deadline_seconds,
        )
        return jsonify({"ok": sent == 1, "task_id": task_id}), 202

    @app.post("/api/tasks/<task_id>/complete")
    def api_complete_task(task_id: str):
        leader_id = monitor.status().get("leader_id")
        if leader_id is None:
            return jsonify({"error": "no elected leader"}), 409
        sent = monitor.send_control([int(leader_id)], "complete_task", task_id=task_id)
        return jsonify({"ok": sent == 1, "task_id": task_id})

    @app.post("/api/tasks/<task_id>/fail")
    def api_fail_task(task_id: str):
        leader_id = monitor.status().get("leader_id")
        if leader_id is None:
            return jsonify({"error": "no elected leader"}), 409
        sent = monitor.send_control([int(leader_id)], "fail_task", task_id=task_id)
        return jsonify({"ok": sent == 1, "task_id": task_id})

    @app.get("/api/metrics/export")
    def api_metrics_export():
        directory = Path(app.config["METRICS_DIR"])
        output_path = export_combined_metrics(directory, directory / "dashboard_metrics.csv", None)
        return send_file(output_path, mimetype="text/csv", as_attachment=True)

    return app


def parse_args() -> argparse.Namespace:
    """Parse dashboard command-line options."""
    parser = argparse.ArgumentParser(description="SwarmNet Flask dashboard")
    parser.add_argument("--n", type=int, required=True, help="Drone count")
    parser.add_argument("--base-port", type=int, default=BASE_PORT, help="Base ZMQ port")
    parser.add_argument("--port", type=int, default=DASHBOARD_PORT, help="HTTP port")
    return parser.parse_args()


def main() -> None:
    """Run the Phase 4 dashboard service."""
    args = parse_args()
    monitor = DashboardMonitor(args.n, args.base_port)
    monitor.start()
    app = create_app(monitor)
    try:
        app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
    finally:
        monitor.close()


if __name__ == "__main__":
    main()
