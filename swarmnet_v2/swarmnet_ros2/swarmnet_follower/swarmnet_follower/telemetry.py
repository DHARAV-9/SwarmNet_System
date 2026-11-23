"""Track independently received measurements without depending on ROS clocks."""

from dataclasses import dataclass
from math import isfinite, nan

from swarmnet_follower.frames import LocalFrame, Vector3

UNKNOWN_VECTOR = (nan, nan, nan)


@dataclass(frozen=True)
class StateReading:
    position: Vector3
    velocity: Vector3
    battery_percent: float
    alive: bool
    comms_healthy: bool


@dataclass
class Telemetry:
    timeout_s: float
    battery_timeout_s: float = 5.0
    position: tuple[Vector3, float] | None = None
    velocity: tuple[Vector3, float] | None = None
    battery: tuple[float, float] | None = None
    heartbeat: tuple[bool, float] | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.timeout_s) or self.timeout_s <= 0:
            raise ValueError("telemetry_timeout_s must be finite and positive")
        if not isfinite(self.battery_timeout_s) or self.battery_timeout_s <= 0:
            raise ValueError("battery_timeout_s must be finite and positive")

    def update_connection(self, connected: bool, received_at: float) -> None:
        if not connected:
            self.position = self.velocity = self.battery = None
        self.heartbeat = connected, received_at

    def connected(self, now: float) -> bool:
        return self.heartbeat is not None and self.heartbeat[0] and self._fresh(self.heartbeat[1], now)

    def _fresh(self, received_at: float, now: float) -> bool:
        return 0.0 <= now - received_at < self.timeout_s

    def snapshot(self, now: float, frame: LocalFrame | None) -> StateReading:
        connected = self.connected(now)
        position = UNKNOWN_VECTOR
        velocity = UNKNOWN_VECTOR
        battery = nan
        if connected:
            if frame is not None and self.position and self._fresh(self.position[1], now):
                if all(map(isfinite, self.position[0])):
                    position = frame.local_to_world(self.position[0])
            if self.velocity and self._fresh(self.velocity[1], now):
                if all(map(isfinite, self.velocity[0])):
                    velocity = self.velocity[0]
            if self.battery and 0.0 <= now - self.battery[1] < self.battery_timeout_s:
                if 0.0 <= self.battery[0] <= 1.0:
                    battery = 100.0 * self.battery[0]
        healthy = connected and all(map(isfinite, (*position, *velocity, battery)))
        return StateReading(position, velocity, battery, healthy, healthy)
