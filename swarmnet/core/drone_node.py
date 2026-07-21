"""
drone_node.py — Main DroneNode process.

Each drone runs as an independent process with its own event loop.
It orchestrates:
  - ZeroMQ messaging (via Messenger)
  - Raft consensus (via RaftStateMachine)
  - Gossip state synchronization (via GossipAgent)
  - State broadcasting (via PUB socket)
  - Battery simulation

Usage (spawned by launcher.py):
    python -m swarmnet.core.drone_node --id 0 --n 5 --loss 0.0 --seed 42
"""

from __future__ import annotations

import argparse
import logging
import random
import signal
import sys
import time

from swarmnet.comms.fault_sim import FaultSimulator
from swarmnet.comms.messenger import Messenger
from swarmnet.consensus.raft import RaftStateMachine
from swarmnet.core.config import (
    BATTERY_DRAIN_RATE,
    BID_WINDOW_MS,
    EXPORT_CSV,
    FLOCKING_TICK_MS,
    METRICS_DIR,
    TASK_FAILURE_TIMEOUT_MS,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from swarmnet.core.state import DroneState
from swarmnet.flocking.formation import formation_target, normalize_formation_shape
from swarmnet.flocking.reynolds import FlockingConfig, Vector2D, compute_next_state
from swarmnet.gossip.gossip_agent import GossipAgent
from swarmnet.metrics.collector import MetricsCollector
from swarmnet.tasks.allocator import (
    TaskAllocator,
    make_task_command,
    parse_task_command,
)
from swarmnet.tasks.task import Task, TaskStatus

logger = logging.getLogger(__name__)


class DroneNode:
    """A single autonomous drone process.

    Args:
        drone_id:  Unique integer identifier (0 … N-1).
        n_total:   Total number of drones in the cluster.
        loss_rate: Packet loss rate for fault simulation.
        seed:      Random seed for reproducibility.
    """

    def __init__(
        self,
        drone_id: int,
        n_total: int,
        loss_rate: float = 0.0,
        seed: int | None = None,
    ) -> None:
        self.drone_id = drone_id
        self.n_total = n_total
        self._running = False

        # Seed for reproducibility
        rng = random.Random(seed)
        node_seed = rng.randint(0, 2**31) if seed is not None else None

        # --- Build peer list ---
        peer_ids = [i for i in range(n_total) if i != drone_id]

        # --- Initialize state ---
        self.state = DroneState(
            drone_id=drone_id,
            x=rng.uniform(100, WORLD_WIDTH - 100),
            y=rng.uniform(100, WORLD_HEIGHT - 100),
            peers=peer_ids,
        )

        # --- Communications ---
        self.fault_sim = FaultSimulator(loss_rate, seed=node_seed)
        self.messenger = Messenger(drone_id, peer_ids, self.fault_sim)

        # --- Consensus ---
        self.raft = RaftStateMachine(
            self.state, self.messenger, n_total, seed=node_seed
        )

        # --- Metrics ---
        self.metrics = MetricsCollector(
            n_total,
            drone_id=drone_id,
            packet_loss=loss_rate,
        )
        self.raft.on_election_complete = self.metrics.record_election

        # --- Gossip state sync ---
        self.gossip = GossipAgent(
            self.state,
            self.messenger,
            self.metrics,
            seed=node_seed,
        )

        # --- Contract Net task allocation ---
        self.tasks = TaskAllocator(drone_id, bid_window_ms=BID_WINDOW_MS)
        self._pending_task_failures: set[str] = set()

        # --- Flocking behavior ---
        self.flocking_config = FlockingConfig()
        self._waypoint = Vector2D(WORLD_WIDTH / 2, WORLD_HEIGHT / 2)
        self._formation_shape = "v"
        self._waypoint_announced_term: int | None = None
        self._last_flocking_tick = time.monotonic()
        self._last_formation_metric = 0.0
        self._last_formation_error = 0.0
        self._last_message_metric = time.monotonic()
        self._last_sent_count = 0

        # --- Timing ---
        self._last_broadcast = 0.0
        self._last_battery_tick = time.monotonic()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Enter the main event loop.  Blocks until ``stop()`` is called."""
        self._running = True
        logger.info(
            "[DRONE %d] Online at (%.0f, %.0f) | peers=%s",
            self.drone_id,
            self.state.x,
            self.state.y,
            self.state.peers,
        )

        try:
            while self._running and self.state.alive:
                self._tick()
                # Small sleep to avoid busy-waiting (~1 ms tick)
                time.sleep(0.001)
        except KeyboardInterrupt:
            pass
        finally:
            self._shutdown()

    def stop(self) -> None:
        """Request graceful shutdown from another thread."""
        self._running = False

    # ------------------------------------------------------------------
    # Per-tick logic
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        """One iteration of the main loop."""
        now = time.monotonic()

        # 1. Drain network messages once, then route by protocol.
        messages = self.messenger.drain_all(timeout_ms=1)
        gossip_messages = [msg for msg in messages if msg.get("type") == "gossip"]
        control_messages = [msg for msg in messages if msg.get("type") == "control"]
        task_messages = [
            msg for msg in messages if msg.get("type") in {"task_bid", "task_confirm"}
        ]
        raft_messages = [
            msg
            for msg in messages
            if msg.get("type") not in {"gossip", "control", "task_bid", "task_confirm"}
        ]

        # 2. Raft tick (election, heartbeat, message processing)
        self.raft.tick(raft_messages)

        # 3. Apply external controls and committed consensus commands
        self._handle_control_messages(control_messages)
        self._announce_waypoint_if_leader()
        self._apply_committed_commands()
        self._handle_task_messages(task_messages)
        self._tick_task_allocation(now)
        self._detect_failed_task_assignees()

        # 4. Merge incoming gossip before computing flocking
        for msg in gossip_messages:
            self.gossip.handle_message(msg)

        # 5. Battery drain simulation
        dt = now - self._last_battery_tick
        self._last_battery_tick = now
        self.state.battery = max(0.0, self.state.battery - BATTERY_DRAIN_RATE * dt)

        # 6. Reynolds flocking movement
        self._tick_flocking(now)

        # 7. Gossip tick after movement so outgoing state is fresh
        self.gossip.tick([], now=now)

        # 8. Record outgoing message throughput once per second.
        self._record_message_rate(now)

        # 9. Broadcast state to visualizer/dashboard every ~50 ms
        if (now - self._last_broadcast) * 1000 >= 50:
            self.messenger.broadcast(self._broadcast_payload())
            self._last_broadcast = now

        # 10. Print periodic status to terminal
        self._print_status(now)

    def _tick_flocking(self, now: float) -> None:
        """Advance this drone's local position using Reynolds flocking."""
        elapsed_ms = (now - self._last_flocking_tick) * 1000
        if elapsed_ms < FLOCKING_TICK_MS:
            return

        dt_ticks = elapsed_ms / FLOCKING_TICK_MS
        self._last_flocking_tick = now
        target = formation_target(
            self._waypoint,
            self.drone_id,
            self.n_total,
            self._formation_shape,
        )
        step = compute_next_state(
            self.state,
            self.gossip.state_table.entries.values(),
            target,
            self.flocking_config,
            dt_ticks=dt_ticks,
            bounds=(WORLD_WIDTH, WORLD_HEIGHT),
        )
        self.state.x = step.position.x
        self.state.y = step.position.y
        self.state.vx = step.velocity.x
        self.state.vy = step.velocity.y

        if now - self._last_formation_metric >= 1.0:
            error = step.position.distance_to(target)
            self.metrics.record_formation(error)
            self._last_formation_error = error
            self._last_formation_metric = now

    def _record_message_rate(self, now: float) -> None:
        """Record this node's successful outbound messages per second."""
        elapsed = now - self._last_message_metric
        if elapsed < 1.0:
            return
        sent_since_last = self.messenger.sent_count - self._last_sent_count
        self.metrics.record_message_rate(sent_since_last / elapsed)
        self._last_sent_count = self.messenger.sent_count
        self._last_message_metric = now

    def _broadcast_payload(self) -> dict:
        """Return live state plus dashboard-only operational diagnostics."""
        payload = self.state.to_broadcast_dict()
        payload["diagnostics"] = {
            "gossip_rounds": self.gossip.last_convergence_rounds,
            "formation_error": self._last_formation_error,
            "message_rate": self.metrics.records[-1].value
            if self.metrics.records and self.metrics.records[-1].event_type == "message_rate"
            else 0.0,
            "messages_sent": self.messenger.sent_count,
            "messages_dropped": self.fault_sim.dropped_count,
            "packet_loss": self.fault_sim.loss_rate,
        }
        payload["tasks"] = self.tasks.task_summaries()
        return payload

    def _handle_control_messages(self, messages: list[dict]) -> None:
        """Handle visualizer control messages."""
        for msg in messages:
            command = msg.get("command")
            if command == "kill":
                logger.warning("[DRONE %d] Fault injection: stopping node", self.drone_id)
                self.state.alive = False
                self._running = False
                continue
            if command == "set_packet_loss":
                try:
                    rate = float(msg["rate"])
                    self.fault_sim.set_loss_rate(rate)
                    self.metrics.packet_loss = rate
                except (KeyError, TypeError, ValueError) as exc:
                    logger.warning("[DRONE %d] Invalid packet-loss control: %s", self.drone_id, exc)
                continue
            if command == "set_flocking":
                self._apply_flocking_control(msg)
                continue

            if self.state.raft_state != "leader":
                if self.state.leader_id is not None:
                    self.messenger.send_to(self.state.leader_id, msg)
                continue

            if command == "move_waypoint":
                dx = float(msg.get("dx", 0.0))
                dy = float(msg.get("dy", 0.0))
                self._set_waypoint(self._waypoint.x + dx, self._waypoint.y + dy)
                self._replicate_waypoint_command()
            elif command == "set_waypoint":
                self._set_waypoint(float(msg["x"]), float(msg["y"]))
                self._replicate_waypoint_command()
            elif command == "set_formation":
                self._formation_shape = normalize_formation_shape(msg.get("shape"))
                self._replicate_waypoint_command()
            elif command == "announce_task":
                self._replicate_task_announcement(msg)
            elif command == "complete_task":
                self._replicate_task_completion(str(msg.get("task_id", "")))
            elif command == "fail_task":
                self._replicate_task_failure(str(msg.get("task_id", "")))

    def _apply_flocking_control(self, msg: dict) -> None:
        """Apply runtime flocking weight and speed controls."""
        self.flocking_config = FlockingConfig(
            neighbor_radius=float(
                msg.get("neighbor_radius", self.flocking_config.neighbor_radius)
            ),
            min_sep_dist=float(
                msg.get("min_sep_dist", self.flocking_config.min_sep_dist)
            ),
            max_speed=float(msg.get("max_speed", self.flocking_config.max_speed)),
            w_sep=float(msg.get("w_sep", self.flocking_config.w_sep)),
            w_ali=float(msg.get("w_ali", self.flocking_config.w_ali)),
            w_coh=float(msg.get("w_coh", self.flocking_config.w_coh)),
            w_way=float(msg.get("w_way", self.flocking_config.w_way)),
        )

    def _set_waypoint(self, x: float, y: float) -> None:
        """Clamp and set the shared waypoint."""
        self._waypoint = Vector2D(
            min(max(float(x), 0.0), WORLD_WIDTH),
            min(max(float(y), 0.0), WORLD_HEIGHT),
        )

    def _announce_waypoint_if_leader(self) -> None:
        """Publish this term's current waypoint through the Raft log."""
        if self.state.raft_state != "leader":
            return
        if self._waypoint_announced_term == self.state.current_term:
            return
        if self._replicate_waypoint_command():
            self._waypoint_announced_term = self.state.current_term

    def _replicate_waypoint_command(self) -> bool:
        """Replicate the current waypoint and formation through Raft."""
        command = (
            f"WAYPOINT {self._waypoint.x:.2f} "
            f"{self._waypoint.y:.2f} {self._formation_shape}"
        )
        return self.raft.replicate_command(command)

    def _replicate_task_announcement(self, msg: dict) -> bool:
        """Ask the leader to announce a new task through the Raft log."""
        task_id = str(msg.get("task_id", "")).strip()
        if not task_id:
            logger.warning("[DRONE %d] Task announcement missing task_id", self.drone_id)
            return False
        try:
            task = Task(
                task_id=task_id,
                description=str(msg.get("description", task_id)),
                x=float(msg["x"]),
                y=float(msg["y"]),
                deadline=time.time() + max(0.0, float(msg.get("deadline_seconds", 60.0))),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("[DRONE %d] Invalid task announcement: %s", self.drone_id, exc)
            return False
        return self.raft.replicate_command(make_task_command("announce", task=task.to_dict()))

    def _replicate_task_completion(self, task_id: str) -> bool:
        """Commit completion of an in-progress task."""
        task = self.tasks.tasks.get(task_id)
        if task is None or task.status != TaskStatus.IN_PROGRESS:
            return False
        return self.raft.replicate_command(make_task_command("done", task_id=task_id))

    def _replicate_task_failure(self, task_id: str) -> bool:
        """Commit failure of an active task so the leader can re-announce it."""
        task = self.tasks.tasks.get(task_id)
        if task is None or task.status in {TaskStatus.DONE, TaskStatus.FAILED}:
            return False
        return self.raft.replicate_command(make_task_command("fail", task_id=task_id))

    def _handle_task_messages(self, messages: list[dict]) -> None:
        """Accept bids and task confirmations only on the current leader."""
        if self.state.raft_state != "leader":
            return
        for msg in messages:
            if msg.get("type") == "task_bid":
                try:
                    self.tasks.submit_bid(
                        str(msg["task_id"]),
                        int(msg["bidder_id"]),
                        float(msg["score"]),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
            elif msg.get("type") == "task_confirm":
                task_id = str(msg.get("task_id", ""))
                drone_id = int(msg.get("drone_id", -1))
                task = self.tasks.tasks.get(task_id)
                if task is not None and task.status == TaskStatus.AWARDED and task.assigned_to == drone_id:
                    self.raft.replicate_command(
                        make_task_command("start", task_id=task_id, drone_id=drone_id)
                    )

    def _tick_task_allocation(self, now: float) -> None:
        """Submit local bids and let the leader award expired auctions."""
        bid = self.tasks.local_bid(self.state)
        if bid is not None:
            task_id, score = bid
            if self.state.raft_state == "leader":
                self.tasks.submit_bid(task_id, self.drone_id, score)
            elif self.state.leader_id is not None:
                self.messenger.send_to(
                    self.state.leader_id,
                    {
                        "type": "task_bid",
                        "task_id": task_id,
                        "bidder_id": self.drone_id,
                        "score": score,
                    },
                )

        if self.state.raft_state == "leader":
            winner = self.tasks.award_ready(now)
            if winner is not None and winner.assigned_to is not None:
                self.raft.replicate_command(
                    make_task_command(
                        "award",
                        task_id=winner.task_id,
                        drone_id=winner.assigned_to,
                    )
                )

    def _detect_failed_task_assignees(self) -> None:
        """Re-open active tasks whose assigned drone is no longer gossip-fresh."""
        if self.state.raft_state != "leader":
            return
        stale_after = TASK_FAILURE_TIMEOUT_MS / 1000
        current_time = time.time()
        for task in self.tasks.tasks.values():
            if task.status not in {TaskStatus.AWARDED, TaskStatus.IN_PROGRESS}:
                continue
            if task.assigned_to is None or task.task_id in self._pending_task_failures:
                continue
            if task.assigned_to == self.drone_id:
                continue
            entry = self.gossip.state_table.get(task.assigned_to)
            is_stale = entry is None or current_time - entry.timestamp > stale_after
            if is_stale and self._replicate_task_failure(task.task_id):
                self._pending_task_failures.add(task.task_id)

    def _apply_committed_commands(self) -> None:
        """Apply committed Raft log entries to local behavior state."""
        while self.state.last_applied < self.state.commit_index:
            entry = self.state.log[self.state.last_applied]
            self._apply_command(str(entry.get("command", "")))
            self.state.last_applied += 1

    def _apply_command(self, command: str) -> None:
        """Apply a committed swarm command."""
        task_command = parse_task_command(command)
        if task_command is not None:
            self._apply_task_command(task_command)
            return
        parts = command.split()
        if len(parts) >= 4 and parts[0] == "WAYPOINT":
            self._set_waypoint(float(parts[1]), float(parts[2]))
            self._formation_shape = normalize_formation_shape(parts[3])

    def _apply_task_command(self, command: dict[str, object]) -> None:
        """Apply one committed Contract Net lifecycle transition."""
        action = command.get("action")
        if action == "announce" and isinstance(command.get("task"), dict):
            task = Task.from_dict(command["task"])
            self.tasks.announce(task)
            self._pending_task_failures.discard(task.task_id)
        elif action == "award":
            self.tasks.award(str(command.get("task_id", "")), int(command.get("drone_id", -1)))
            task = self.tasks.tasks.get(str(command.get("task_id", "")))
            if task is not None and task.assigned_to == self.drone_id:
                if self.state.raft_state == "leader":
                    self.raft.replicate_command(
                        make_task_command("start", task_id=task.task_id, drone_id=self.drone_id)
                    )
                elif self.state.leader_id is not None:
                    self.messenger.send_to(
                        self.state.leader_id,
                        {"type": "task_confirm", "task_id": task.task_id, "drone_id": self.drone_id},
                    )
        elif action == "start":
            task_id = str(command.get("task_id", ""))
            drone_id = int(command.get("drone_id", -1))
            if self.tasks.confirm(task_id, drone_id) and drone_id == self.drone_id:
                self.state.task = task_id
        elif action == "done":
            task_id = str(command.get("task_id", ""))
            if self.tasks.complete(task_id) and self.state.task == task_id:
                self.state.task = None
        elif action == "fail":
            task_id = str(command.get("task_id", ""))
            replacement = self.tasks.fail(task_id)
            self._pending_task_failures.discard(task_id)
            if self.state.task == task_id:
                self.state.task = None
            if replacement is not None and self.state.raft_state == "leader":
                self.raft.replicate_command(
                    make_task_command("announce", task=replacement.to_dict())
                )

    _last_status_print = 0.0

    def _print_status(self, now: float) -> None:
        """Print a one-line status every 2 seconds."""
        if now - self._last_status_print < 2.0:
            return
        self._last_status_print = now

        leader_str = (
            f"leader={self.state.leader_id}"
            if self.state.leader_id is not None
            else "leader=?"
        )
        print(
            f"[DRONE {self.drone_id}] "
            f"state={self.state.raft_state:<10s} "
            f"term={self.state.current_term:<3d} "
            f"{leader_str:<12s} "
            f"battery={self.state.battery:.1f}% "
            f"gossip={len(self.gossip.state_table)}/{self.n_total}"
        )

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _shutdown(self) -> None:
        """Clean up resources."""
        self.state.alive = False
        if EXPORT_CSV and self.metrics.records:
            try:
                self.metrics.export_csv(
                    f"{METRICS_DIR}/drone_{self.drone_id}_metrics.csv"
                )
            except OSError as exc:
                logger.warning(
                    "[DRONE %d] Metrics export failed: %s",
                    self.drone_id,
                    exc,
                )
        self.messenger.close()
        logger.info("[DRONE %d] Shut down", self.drone_id)


# ======================================================================
# Entry point (when run as a subprocess)
# ======================================================================

def main() -> None:
    """Parse CLI args and start a single DroneNode."""
    parser = argparse.ArgumentParser(description="SwarmNet DroneNode process")
    parser.add_argument("--id", type=int, required=True, help="Drone ID (0-indexed)")
    parser.add_argument("--n", type=int, required=True, help="Total drone count")
    parser.add_argument("--loss", type=float, default=0.0, help="Packet loss rate")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s [DRONE {args.id}] %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    node = DroneNode(
        drone_id=args.id,
        n_total=args.n,
        loss_rate=args.loss,
        seed=args.seed,
    )

    # Graceful shutdown on SIGTERM
    def _signal_handler(signum, frame):
        logger.info("[DRONE %d] Received signal %d, shutting down...", args.id, signum)
        node.stop()

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    node.run()


if __name__ == "__main__":
    main()
