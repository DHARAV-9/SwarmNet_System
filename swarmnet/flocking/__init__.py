"""Flocking behavior package for SwarmNet."""

from swarmnet.flocking.formation import (
    FORMATION_SHAPES,
    formation_target,
    normalize_formation_shape,
)
from swarmnet.flocking.reynolds import (
    FlockingConfig,
    FlockingStep,
    Vector2D,
    compute_next_state,
)

__all__ = [
    "FORMATION_SHAPES",
    "FlockingConfig",
    "FlockingStep",
    "Vector2D",
    "compute_next_state",
    "formation_target",
    "normalize_formation_shape",
]
