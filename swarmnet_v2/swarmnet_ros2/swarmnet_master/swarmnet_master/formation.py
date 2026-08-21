"""Phase 2 grid formation helpers shared by the master node and tests."""

from __future__ import annotations

from dataclasses import dataclass


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
    grid_width: int = 7,
    spacing_m: float = 2.0,
    altitude_m: float = 5.0,
) -> list[FormationTarget]:
    """Return the centered 7×7 grid targets defined by the V2 TRD."""
    if not 1 <= n_drones <= 50:
        raise ValueError("n_drones must be between 1 and 50")
    midpoint = (grid_width - 1) / 2
    targets: list[FormationTarget] = []
    for drone_id in range(1, n_drones + 1):
        row, col = divmod(drone_id - 1, grid_width)
        targets.append(
            FormationTarget(
                drone_id=drone_id,
                x=(col - midpoint) * spacing_m,
                y=(row - midpoint) * spacing_m,
                z=altitude_m,
            )
        )
    return targets
