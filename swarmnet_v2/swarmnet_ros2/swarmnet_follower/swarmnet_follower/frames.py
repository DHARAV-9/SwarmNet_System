"""Frame conversions for a fixed, east/north/up-aligned vehicle origin."""

from dataclasses import dataclass
from math import isfinite

Vector3 = tuple[float, float, float]


def local_enu_to_px4_ned(vector: Vector3) -> Vector3:
    """Convert a local position or vector from ENU to PX4 NED."""
    east, north, up = vector
    return north, east, -up


def px4_ned_to_local_enu(vector: Vector3) -> Vector3:
    """Convert a local position or vector from PX4 NED to ENU."""
    north, east, down = vector
    return east, north, -down


@dataclass(frozen=True)
class LocalFrame:
    """Vehicle-local ENU origin, expressed in shared world ENU meters."""

    origin_world_enu: Vector3

    def __post_init__(self) -> None:
        if len(self.origin_world_enu) != 3 or not all(map(isfinite, self.origin_world_enu)):
            raise ValueError("local_origin_world_enu must contain three finite coordinates")

    def local_to_world(self, position: Vector3) -> Vector3:
        east, north, up = position
        origin_east, origin_north, origin_up = self.origin_world_enu
        return east + origin_east, north + origin_north, up + origin_up

    def world_to_local(self, position: Vector3) -> Vector3:
        east, north, up = position
        origin_east, origin_north, origin_up = self.origin_world_enu
        return east - origin_east, north - origin_north, up - origin_up
