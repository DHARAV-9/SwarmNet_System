"""
formation.py - Formation target helpers for SwarmNet flocking.

The leader waypoint is converted into a per-drone target offset for V-shape,
grid, or circle formations.
"""

from __future__ import annotations

import math

from swarmnet.flocking.reynolds import Vector2D

FORMATION_SHAPES = {"v", "grid", "circle"}
DEFAULT_SPACING = 60.0


def normalize_formation_shape(shape: str | None) -> str:
    """Return a supported formation shape, defaulting to V-shape."""
    if not shape:
        return "v"
    normalized = shape.strip().lower()
    return normalized if normalized in FORMATION_SHAPES else "v"


def formation_offset(
    drone_id: int,
    n_total: int,
    shape: str = "v",
    spacing: float = DEFAULT_SPACING,
) -> Vector2D:
    """Return this drone's offset from the leader waypoint."""
    shape = normalize_formation_shape(shape)
    n_total = max(1, n_total)

    if shape == "grid":
        columns = math.ceil(math.sqrt(n_total))
        rows = math.ceil(n_total / columns)
        row = drone_id // columns
        column = drone_id % columns
        x = (column - (columns - 1) / 2) * spacing
        y = (row - (rows - 1) / 2) * spacing
        return Vector2D(x, y)

    if shape == "circle":
        radius = max(spacing, n_total * spacing / (2 * math.pi))
        angle = (2 * math.pi * drone_id) / n_total
        return Vector2D(math.cos(angle) * radius, math.sin(angle) * radius)

    if drone_id == 0:
        return Vector2D(0.0, 0.0)

    rank = (drone_id + 1) // 2
    side = -1.0 if drone_id % 2 else 1.0
    return Vector2D(side * rank * spacing, rank * spacing)


def formation_target(
    waypoint: Vector2D | tuple[float, float],
    drone_id: int,
    n_total: int,
    shape: str = "v",
    spacing: float = DEFAULT_SPACING,
) -> Vector2D:
    """Return the absolute target point for a drone in formation."""
    if isinstance(waypoint, Vector2D):
        base = waypoint
    else:
        base = Vector2D(float(waypoint[0]), float(waypoint[1]))
    return base + formation_offset(drone_id, n_total, shape, spacing)
