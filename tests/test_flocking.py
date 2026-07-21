"""
test_flocking.py - Unit tests for Reynolds flocking and formations.
"""

from __future__ import annotations

import math

from swarmnet.core.state import DroneState
from swarmnet.flocking.formation import formation_target
from swarmnet.flocking.reynolds import (
    FlockingConfig,
    Vector2D,
    alignment_force,
    cohesion_force,
    compute_next_state,
    separation_force,
)
from swarmnet.gossip.state_table import StateTableEntry


def make_entry(
    drone_id: int,
    x: float,
    y: float,
    vx: float = 0.0,
    vy: float = 0.0,
) -> StateTableEntry:
    """Build a table entry for flocking tests."""
    return StateTableEntry(
        drone_id=drone_id,
        x=x,
        y=y,
        vx=vx,
        vy=vy,
        battery=100.0,
        task=None,
        raft_state="follower",
        term=1,
        timestamp=1.0,
    )


def test_separation_steers_away_from_close_neighbor():
    own_position = Vector2D(0.0, 0.0)
    neighbor = make_entry(1, 10.0, 0.0)

    force = separation_force(own_position, [neighbor], min_sep_dist=30.0)

    assert force.x < 0
    assert abs(force.y) < 1e-9


def test_alignment_steers_toward_average_neighbor_velocity():
    force = alignment_force(
        Vector2D(0.0, 0.0),
        [make_entry(1, 10.0, 0.0, vx=2.0, vy=0.0)],
    )

    assert force.x > 0
    assert abs(force.y) < 1e-9


def test_cohesion_steers_toward_neighbor_center():
    force = cohesion_force(
        Vector2D(0.0, 0.0),
        [make_entry(1, 10.0, 0.0), make_entry(2, 20.0, 0.0)],
    )

    assert force.x > 0
    assert abs(force.y) < 1e-9


def test_compute_next_state_limits_speed_and_moves_toward_target():
    state = DroneState(drone_id=0, x=0.0, y=0.0, vx=20.0, vy=0.0)
    config = FlockingConfig(max_speed=5.0, w_sep=0.0, w_ali=0.0, w_coh=0.0)

    step = compute_next_state(
        state,
        known_entries=[],
        target=Vector2D(100.0, 0.0),
        config=config,
        dt_ticks=1.0,
    )

    assert step.velocity.magnitude <= 5.0
    assert step.position.x > state.x


def test_grid_formation_targets_are_centered_around_waypoint():
    waypoint = Vector2D(400.0, 300.0)
    targets = [formation_target(waypoint, i, n_total=4, shape="grid") for i in range(4)]
    avg_x = sum(target.x for target in targets) / len(targets)
    avg_y = sum(target.y for target in targets) / len(targets)

    assert avg_x == 400.0
    assert avg_y == 300.0


def test_circle_formation_places_targets_on_common_radius():
    waypoint = Vector2D(400.0, 300.0)
    targets = [
        formation_target(waypoint, i, n_total=6, shape="circle") for i in range(6)
    ]
    radii = [target.distance_to(waypoint) for target in targets]

    assert max(radii) - min(radii) < 1e-9
    assert math.isclose(radii[0], 60.0, rel_tol=1e-9)


def test_v_formation_keeps_leader_at_waypoint():
    waypoint = Vector2D(400.0, 300.0)

    assert formation_target(waypoint, 0, n_total=5, shape="v") == waypoint
    assert formation_target(waypoint, 1, n_total=5, shape="v").y > waypoint.y
