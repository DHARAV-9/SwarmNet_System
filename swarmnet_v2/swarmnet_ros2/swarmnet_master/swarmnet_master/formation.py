"""Phase 2 grid formation helpers shared by the master node and tests."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from swarmnet_master.routing import validate_fleet_size

DEFAULT_GRID_WIDTH = 10
DEFAULT_SPACING_M = 2.0
DEFAULT_ALTITUDE_M = 5.0


@dataclass(frozen=True)
class FormationTarget:
    """A static hold target assigned to one simulated drone."""

    drone_id: int
    x: float
    y: float
    z: float
    yaw: float = 0.0


def grid_targets(
    n_drones: int,
    grid_width: int = DEFAULT_GRID_WIDTH,
    spacing_m: float = DEFAULT_SPACING_M,
    altitude_m: float = DEFAULT_ALTITUDE_M,
) -> list[FormationTarget]:
    """Lay out centered rows with up to ten columns by default."""
    validate_fleet_size(n_drones)
    if grid_width < 1 or not isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError("grid width and spacing must be positive")
    if not isfinite(altitude_m) or altitude_m <= 0:
        raise ValueError("hover altitude must be finite and positive")
    n_rows = (n_drones + grid_width - 1) // grid_width
    targets: list[FormationTarget] = []
    for drone_id in range(1, n_drones + 1):
        row, col = divmod(drone_id - 1, grid_width)
        row_width = min(grid_width, n_drones - row * grid_width)
        targets.append(
            FormationTarget(
                drone_id=drone_id,
                x=(col - (row_width - 1) / 2) * spacing_m,
                y=(row - (n_rows - 1) / 2) * spacing_m,
                z=altitude_m,
            )
        )
    return targets
