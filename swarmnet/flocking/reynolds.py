"""
reynolds.py - Reynolds flocking rules for SwarmNet.

Implements separation, alignment, cohesion, and waypoint steering in pure
Python so the behavior can be tested independently of the drone process loop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from swarmnet.core.config import (
    MAX_SPEED,
    MIN_SEP_DIST,
    NEIGHBOR_RADIUS,
    W_ALI,
    W_COH,
    W_SEP,
    W_WAY,
)
from swarmnet.core.state import DroneState
from swarmnet.gossip.state_table import StateTableEntry


@dataclass(frozen=True)
class Vector2D:
    """Small immutable 2-D vector helper."""

    x: float
    y: float

    def __add__(self, other: Vector2D) -> Vector2D:
        return Vector2D(self.x + other.x, self.y + other.y)

    def __sub__(self, other: Vector2D) -> Vector2D:
        return Vector2D(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> Vector2D:
        return Vector2D(self.x * scalar, self.y * scalar)

    def __truediv__(self, scalar: float) -> Vector2D:
        if scalar == 0:
            return Vector2D(0.0, 0.0)
        return Vector2D(self.x / scalar, self.y / scalar)

    @property
    def magnitude(self) -> float:
        """Return Euclidean length."""
        return math.hypot(self.x, self.y)

    def normalized(self) -> Vector2D:
        """Return a unit vector, or zero if this vector is zero."""
        length = self.magnitude
        if length == 0:
            return Vector2D(0.0, 0.0)
        return self / length

    def limited(self, max_magnitude: float) -> Vector2D:
        """Return this vector capped to *max_magnitude*."""
        length = self.magnitude
        if length <= max_magnitude or length == 0:
            return self
        return self.normalized() * max_magnitude

    def distance_to(self, other: Vector2D) -> float:
        """Return distance to another point/vector."""
        return (self - other).magnitude

    def to_tuple(self) -> tuple[float, float]:
        """Return ``(x, y)``."""
        return (self.x, self.y)


@dataclass(frozen=True)
class FlockingConfig:
    """Runtime-tunable flocking parameters."""

    neighbor_radius: float = NEIGHBOR_RADIUS
    min_sep_dist: float = MIN_SEP_DIST
    max_speed: float = MAX_SPEED
    w_sep: float = W_SEP
    w_ali: float = W_ALI
    w_coh: float = W_COH
    w_way: float = W_WAY


@dataclass(frozen=True)
class FlockingStep:
    """Result of one flocking update."""

    position: Vector2D
    velocity: Vector2D
    target: Vector2D
    separation: Vector2D
    alignment: Vector2D
    cohesion: Vector2D
    waypoint: Vector2D


def position_of(entry: StateTableEntry | DroneState) -> Vector2D:
    """Return an entry/state position as a vector."""
    return Vector2D(float(entry.x), float(entry.y))


def velocity_of(entry: StateTableEntry | DroneState) -> Vector2D:
    """Return an entry/state velocity as a vector."""
    return Vector2D(float(entry.vx), float(entry.vy))


def neighbors_in_radius(
    own_state: DroneState,
    entries: Iterable[StateTableEntry],
    radius: float,
) -> list[StateTableEntry]:
    """Return entries for other drones within *radius*."""
    own_position = position_of(own_state)
    neighbors: list[StateTableEntry] = []
    for entry in entries:
        if entry.drone_id == own_state.drone_id:
            continue
        if own_position.distance_to(position_of(entry)) <= radius:
            neighbors.append(entry)
    return neighbors


def separation_force(
    own_position: Vector2D,
    neighbors: Iterable[StateTableEntry],
    min_sep_dist: float,
) -> Vector2D:
    """Steer away from neighbors closer than *min_sep_dist*."""
    total = Vector2D(0.0, 0.0)
    for neighbor in neighbors:
        neighbor_position = position_of(neighbor)
        distance = own_position.distance_to(neighbor_position)
        if 0 < distance < min_sep_dist:
            total = total + (own_position - neighbor_position).normalized() / distance
    return total.normalized()


def alignment_force(
    own_velocity: Vector2D,
    neighbors: Iterable[StateTableEntry],
) -> Vector2D:
    """Steer toward the average neighbor velocity."""
    neighbor_list = list(neighbors)
    if not neighbor_list:
        return Vector2D(0.0, 0.0)

    average = Vector2D(0.0, 0.0)
    for neighbor in neighbor_list:
        average = average + velocity_of(neighbor)
    average = average / len(neighbor_list)
    return (average - own_velocity).normalized()


def cohesion_force(
    own_position: Vector2D,
    neighbors: Iterable[StateTableEntry],
) -> Vector2D:
    """Steer toward the center of mass of nearby drones."""
    neighbor_list = list(neighbors)
    if not neighbor_list:
        return Vector2D(0.0, 0.0)

    center = Vector2D(0.0, 0.0)
    for neighbor in neighbor_list:
        center = center + position_of(neighbor)
    center = center / len(neighbor_list)
    return (center - own_position).normalized()


def waypoint_force(own_position: Vector2D, target: Vector2D) -> Vector2D:
    """Steer toward the assigned formation target."""
    return (target - own_position).normalized()


def compute_next_state(
    own_state: DroneState,
    known_entries: Iterable[StateTableEntry],
    target: Vector2D,
    config: FlockingConfig | None = None,
    dt_ticks: float = 1.0,
    bounds: tuple[float, float] | None = None,
) -> FlockingStep:
    """Compute the next position and velocity for one drone."""
    cfg = config or FlockingConfig()
    own_position = position_of(own_state)
    own_velocity = velocity_of(own_state)
    neighbors = neighbors_in_radius(own_state, known_entries, cfg.neighbor_radius)

    separation = separation_force(own_position, neighbors, cfg.min_sep_dist)
    alignment = alignment_force(own_velocity, neighbors)
    cohesion = cohesion_force(own_position, neighbors)
    waypoint = waypoint_force(own_position, target)

    new_velocity = (
        own_velocity
        + separation * cfg.w_sep
        + alignment * cfg.w_ali
        + cohesion * cfg.w_coh
        + waypoint * cfg.w_way
    ).limited(cfg.max_speed)

    new_position = own_position + new_velocity * max(0.0, dt_ticks)
    if bounds is not None:
        new_position, new_velocity = clamp_to_bounds(
            new_position,
            new_velocity,
            bounds[0],
            bounds[1],
        )

    return FlockingStep(
        position=new_position,
        velocity=new_velocity,
        target=target,
        separation=separation,
        alignment=alignment,
        cohesion=cohesion,
        waypoint=waypoint,
    )


def clamp_to_bounds(
    position: Vector2D,
    velocity: Vector2D,
    width: float,
    height: float,
) -> tuple[Vector2D, Vector2D]:
    """Clamp position inside the simulation world and stop wallward velocity."""
    x = min(max(position.x, 0.0), width)
    y = min(max(position.y, 0.0), height)
    vx = 0.0 if x in (0.0, width) and position.x != x else velocity.x
    vy = 0.0 if y in (0.0, height) and position.y != y else velocity.y
    return Vector2D(x, y), Vector2D(vx, vy)
