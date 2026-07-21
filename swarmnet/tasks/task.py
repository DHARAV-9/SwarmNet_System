"""Task model and lifecycle definitions for Contract Net allocation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TaskStatus(str, Enum):
    """States a swarm task can occupy during its lifecycle."""

    OPEN = "open"
    AWARDED = "awarded"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Task:
    """One location-based swarm task announced by the elected leader."""

    task_id: str
    description: str
    x: float
    y: float
    deadline: float
    status: TaskStatus = TaskStatus.OPEN
    assigned_to: int | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable task representation."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "x": self.x,
            "y": self.y,
            "deadline": self.deadline,
            "status": self.status.value,
            "assigned_to": self.assigned_to,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "Task":
        """Create a task from a replicated command payload."""
        return cls(
            task_id=str(payload["task_id"]),
            description=str(payload["description"]),
            x=float(payload["x"]),
            y=float(payload["y"]),
            deadline=float(payload["deadline"]),
            status=TaskStatus(str(payload.get("status", TaskStatus.OPEN.value))),
            assigned_to=(
                int(payload["assigned_to"])
                if payload.get("assigned_to") is not None
                else None
            ),
        )
