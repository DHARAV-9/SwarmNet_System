"""Single source of truth for PX4, MAVROS, and QGC simulation endpoints."""

from dataclasses import dataclass

MAX_VEHICLES = 254
QGC_PORT = 14550


def validate_fleet_size(count: int) -> None:
    if not 1 <= count <= MAX_VEHICLES:
        raise ValueError("fleet size must be 1–254 (MAVLink ID 0 is invalid; 255 is reserved for GCS)")


@dataclass(frozen=True)
class VehicleRoute:
    drone_id: int

    def __post_init__(self) -> None:
        validate_fleet_size(self.drone_id)

    @property
    def instance(self) -> int:
        return self.drone_id - 1

    @property
    def offboard_port(self) -> int:
        return 15000 + self.instance

    @property
    def mavros_port(self) -> int:
        return 16000 + self.instance

    @property
    def gcs_source_port(self) -> int:
        return 18570 + self.instance

    @property
    def namespace(self) -> str:
        return f"drone_{self.drone_id}/mavros"

    @property
    def state_dir(self) -> str:
        return f"instance_{self.instance}"

    def fcu_url(self, px4_host: str) -> str:
        return f"udp://:{self.mavros_port}@{px4_host}:{self.offboard_port}"
