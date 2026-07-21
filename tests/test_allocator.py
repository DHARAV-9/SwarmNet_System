"""Tests for Phase 5 Contract Net task allocation."""

from __future__ import annotations

from swarmnet.core.state import DroneState
from swarmnet.tasks.allocator import (
    TaskAllocator,
    make_task_command,
    parse_task_command,
)
from swarmnet.tasks.task import Task, TaskStatus


def make_task(task_id: str = "scan-a") -> Task:
    """Build a deterministic open task."""
    return Task(task_id, "Scan zone A", x=10.0, y=10.0, deadline=1000.0)


def test_highest_bid_wins_task():
    allocator = TaskAllocator(drone_id=0, bid_window_ms=500)
    allocator.announce(make_task(), now=1.0)
    allocator.submit_bid("scan-a", bidder_id=2, score=20.0)
    allocator.submit_bid("scan-a", bidder_id=1, score=30.0)

    winner = allocator.award_ready(now=1.5)

    assert winner is not None
    assert winner.assigned_to == 1
    assert allocator.award("scan-a", winner.assigned_to)
    assert allocator.tasks["scan-a"].status == TaskStatus.AWARDED


def test_tied_bids_choose_lowest_drone_id():
    allocator = TaskAllocator(drone_id=0)
    allocator.announce(make_task(), now=0.0)
    allocator.submit_bid("scan-a", bidder_id=3, score=10.0)
    allocator.submit_bid("scan-a", bidder_id=1, score=10.0)

    assert allocator.award_ready(now=1.0).assigned_to == 1


def test_task_status_transitions():
    allocator = TaskAllocator(drone_id=0)
    allocator.announce(make_task())
    assert allocator.award("scan-a", 2)
    assert allocator.confirm("scan-a", 2)
    assert allocator.complete("scan-a")
    assert allocator.tasks["scan-a"].status == TaskStatus.DONE


def test_task_reassigned_after_drone_failure():
    allocator = TaskAllocator(drone_id=0)
    allocator.announce(make_task())
    allocator.award("scan-a", 2)
    replacement = allocator.fail("scan-a")

    assert allocator.tasks["scan-a"].status == TaskStatus.FAILED
    assert replacement is not None
    assert replacement.status == TaskStatus.OPEN
    assert replacement.assigned_to is None

    allocator.announce(replacement, now=2.0)
    allocator.submit_bid("scan-a", bidder_id=1, score=25.0)
    assert allocator.award_ready(now=3.0).assigned_to == 1


def test_local_bid_uses_battery_and_distance_score():
    allocator = TaskAllocator(drone_id=1)
    allocator.announce(make_task())
    state = DroneState(drone_id=1, x=10.0, y=10.0, battery=80.0)

    task_id, score = allocator.local_bid(state)

    assert task_id == "scan-a"
    assert score == 40.5
    assert allocator.local_bid(state) is None


def test_task_commands_round_trip_as_raft_log_payloads():
    command = make_task_command("award", task_id="scan-a", drone_id=2)

    assert parse_task_command(command) == {
        "action": "award",
        "drone_id": 2,
        "task_id": "scan-a",
    }
    assert parse_task_command("WAYPOINT 1 2 v") is None
