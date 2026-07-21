"""Deterministic Contract Net task bidding and lifecycle management."""

from __future__ import annotations

import json
import math
import time
from typing import Iterable

from swarmnet.core.state import DroneState
from swarmnet.gossip.state_table import StateTableEntry
from swarmnet.tasks.task import Task, TaskStatus

TASK_COMMAND_PREFIX = "TASK "


def make_task_command(action: str, **payload: object) -> str:
    """Encode a task lifecycle action for the replicated Raft log."""
    return TASK_COMMAND_PREFIX + json.dumps(
        {"action": action, **payload},
        separators=(",", ":"),
        sort_keys=True,
    )


def parse_task_command(command: str) -> dict[str, object] | None:
    """Decode a task command, returning ``None`` for unrelated log entries."""
    if not command.startswith(TASK_COMMAND_PREFIX):
        return None
    try:
        payload = json.loads(command[len(TASK_COMMAND_PREFIX) :])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


class TaskAllocator:
    """Manage local task state and choose winners after a bid window."""

    def __init__(self, drone_id: int, bid_window_ms: int = 500) -> None:
        if bid_window_ms <= 0:
            raise ValueError("bid_window_ms must be positive")
        self.drone_id = drone_id
        self.bid_window_ms = bid_window_ms
        self.tasks: dict[str, Task] = {}
        self._bids: dict[str, dict[int, float]] = {}
        self._bid_deadlines: dict[str, float] = {}
        self._submitted_bids: set[str] = set()

    @staticmethod
    def bid_score(battery: float, x: float, y: float, task: Task) -> float:
        """Return the TRD bid score for a drone and a task location."""
        distance = math.hypot(task.x - x, task.y - y)
        distance_component = 1.0 / max(distance, 1.0)
        return (max(0.0, battery) * 0.5) + (distance_component * 0.5)

    def announce(self, task: Task, now: float | None = None) -> None:
        """Register an announced task and begin its leader bid window."""
        self.tasks[task.task_id] = task
        self._bids[task.task_id] = {}
        self._submitted_bids.discard(task.task_id)
        self._bid_deadlines[task.task_id] = (time.monotonic() if now is None else now) + (
            self.bid_window_ms / 1000
        )

    def submit_bid(self, task_id: str, bidder_id: int, score: float) -> bool:
        """Store a bid if the task is open and the score is valid."""
        task = self.tasks.get(task_id)
        if task is None or task.status != TaskStatus.OPEN or not math.isfinite(score):
            return False
        self._bids.setdefault(task_id, {})[bidder_id] = score
        return True

    def local_bid(self, state: DroneState) -> tuple[str, float] | None:
        """Return the next unsubmitted bid for this node, if any."""
        for task in self.tasks.values():
            if task.status == TaskStatus.OPEN and task.task_id not in self._submitted_bids:
                score = self.bid_score(state.battery, state.x, state.y, task)
                self._submitted_bids.add(task.task_id)
                return task.task_id, score
        return None

    def award_ready(self, now: float | None = None) -> Task | None:
        """Choose the highest bidder for one expired leader bid window."""
        current = time.monotonic() if now is None else now
        for task_id, deadline in list(self._bid_deadlines.items()):
            task = self.tasks.get(task_id)
            if task is None or task.status != TaskStatus.OPEN or current < deadline:
                continue
            bids = self._bids.get(task_id, {})
            del self._bid_deadlines[task_id]
            if not bids:
                continue
            winner = min(bids, key=lambda bidder: (-bids[bidder], bidder))
            return Task(
                task_id=task.task_id,
                description=task.description,
                x=task.x,
                y=task.y,
                deadline=task.deadline,
                status=TaskStatus.AWARDED,
                assigned_to=winner,
            )
        return None

    def award(self, task_id: str, drone_id: int) -> bool:
        """Apply a committed award to an open task."""
        task = self.tasks.get(task_id)
        if task is None or task.status != TaskStatus.OPEN:
            return False
        task.status = TaskStatus.AWARDED
        task.assigned_to = drone_id
        return True

    def confirm(self, task_id: str, drone_id: int) -> bool:
        """Mark an awarded task in progress after its winner confirms."""
        task = self.tasks.get(task_id)
        if task is None or task.status != TaskStatus.AWARDED or task.assigned_to != drone_id:
            return False
        task.status = TaskStatus.IN_PROGRESS
        return True

    def complete(self, task_id: str) -> bool:
        """Mark an in-progress task complete."""
        task = self.tasks.get(task_id)
        if task is None or task.status != TaskStatus.IN_PROGRESS:
            return False
        task.status = TaskStatus.DONE
        return True

    def fail(self, task_id: str) -> Task | None:
        """Mark a task failed and return a fresh re-announcement task."""
        task = self.tasks.get(task_id)
        if task is None or task.status in {TaskStatus.DONE, TaskStatus.FAILED}:
            return None
        task.status = TaskStatus.FAILED
        task.assigned_to = None
        replacement = Task(
            task_id=task.task_id,
            description=task.description,
            x=task.x,
            y=task.y,
            deadline=task.deadline,
        )
        return replacement

    def task_summaries(self) -> list[dict[str, object]]:
        """Return tasks in stable order for dashboard broadcasts."""
        return [self.tasks[task_id].to_dict() for task_id in sorted(self.tasks)]

    def known_entries(self, entries: Iterable[StateTableEntry]) -> dict[int, StateTableEntry]:
        """Return gossip entries keyed by drone ID for optional callers."""
        return {entry.drone_id: entry for entry in entries}
