"""
pygame_viz.py - Real-time 2-D visualizer for SwarmNet.

Subscribes to each drone PUB socket, renders positions and velocity vectors,
and sends lightweight control messages for waypoint, formation, and flocking
weight changes.
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass
from typing import Any

import pygame
import zmq

from swarmnet.comms.serializer import decode, encode
from swarmnet.core.config import BASE_PORT, FPS, WORLD_HEIGHT, WORLD_WIDTH
from swarmnet.flocking.formation import formation_target
from swarmnet.flocking.reynolds import FlockingConfig, Vector2D

PANEL_WIDTH = 260
STALE_AFTER_SECONDS = 3.0

BACKGROUND = (18, 24, 33)
PANEL = (28, 35, 46)
GRID = (42, 52, 65)
TEXT = (226, 232, 240)
MUTED = (146, 157, 171)
FOLLOWER = (80, 170, 255)
CANDIDATE = (245, 158, 66)
LEADER = (255, 214, 90)
TARGET = (94, 234, 212)
FORMATION = (113, 128, 150)


@dataclass
class DroneSnapshot:
    """Latest visual state for one drone."""

    drone_id: int
    x: float
    y: float
    vx: float
    vy: float
    raft_state: str
    term: int
    battery: float
    leader_id: int | None
    last_seen: float

    @classmethod
    def from_message(cls, msg: dict[str, Any]) -> DroneSnapshot:
        """Build a snapshot from a state broadcast message."""
        leader_id = msg.get("leader_id")
        return cls(
            drone_id=int(msg["drone_id"]),
            x=float(msg["x"]),
            y=float(msg["y"]),
            vx=float(msg["vx"]),
            vy=float(msg["vy"]),
            raft_state=str(msg["raft_state"]),
            term=int(msg["term"]),
            battery=float(msg["battery"]),
            leader_id=int(leader_id) if leader_id is not None else None,
            last_seen=time.time(),
        )


class PygameVisualizer:
    """Render SwarmNet drone state from PUB broadcasts."""

    def __init__(self, n_total: int, base_port: int, fps: int) -> None:
        self.n_total = n_total
        self.base_port = base_port
        self.fps = fps
        self.snapshots: dict[int, DroneSnapshot] = {}
        self.waypoint = Vector2D(WORLD_WIDTH / 2, WORLD_HEIGHT / 2)
        self.formation_shape = "v"
        self.show_labels = True
        self.show_overlay = True
        self.running = True
        self.flocking = FlockingConfig()
        self.active_slider: str | None = None

        self._ctx = zmq.Context()
        self._poller = zmq.Poller()
        self._subscribers: list[zmq.Socket] = []
        self._push: dict[int, zmq.Socket] = {}
        self._connect_sockets()

        pygame.init()
        self.screen = pygame.display.set_mode((WORLD_WIDTH + PANEL_WIDTH, WORLD_HEIGHT))
        pygame.display.set_caption("SwarmNet Phase 3")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 15)
        self.small_font = pygame.font.SysFont("arial", 12)

    def _connect_sockets(self) -> None:
        """Connect SUB sockets to drones and PUSH sockets for controls."""
        for drone_id in range(self.n_total):
            sub = self._ctx.socket(zmq.SUB)
            sub.setsockopt(zmq.SUBSCRIBE, b"")
            sub.setsockopt(zmq.LINGER, 0)
            sub.connect(f"tcp://127.0.0.1:{self.base_port + 100 + drone_id}")
            self._poller.register(sub, zmq.POLLIN)
            self._subscribers.append(sub)

            push = self._ctx.socket(zmq.PUSH)
            push.setsockopt(zmq.SNDHWM, 100)
            push.setsockopt(zmq.LINGER, 0)
            push.connect(f"tcp://127.0.0.1:{self.base_port + drone_id}")
            self._push[drone_id] = push

    def run(self) -> None:
        """Run the Pygame event/render loop."""
        try:
            while self.running:
                self._receive_updates()
                self._handle_events()
                self._draw()
                self.clock.tick(self.fps)
        finally:
            self.close()

    def _receive_updates(self) -> None:
        """Drain pending state broadcasts."""
        for socket, _ in dict(self._poller.poll(1)).items():
            try:
                msg = decode(socket.recv(zmq.NOBLOCK))
            except (ValueError, zmq.ZMQError):
                continue
            if msg.get("type") == "state_broadcast":
                snapshot = DroneSnapshot.from_message(msg)
                self.snapshots[snapshot.drone_id] = snapshot

    def _handle_events(self) -> None:
        """Handle Pygame input events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                self._handle_key(event.key)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.active_slider = self._slider_at(event.pos)
                if self.active_slider:
                    self._update_slider(self.active_slider, event.pos[0])
            elif event.type == pygame.MOUSEMOTION and self.active_slider:
                self._update_slider(self.active_slider, event.pos[0])
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.active_slider = None

    def _handle_key(self, key: int) -> None:
        """Map keyboard controls to visualizer state and drone commands."""
        if key in (pygame.K_q, pygame.K_ESCAPE):
            self.running = False
        elif key == pygame.K_h:
            self.show_labels = not self.show_labels
        elif key == pygame.K_f:
            self.show_overlay = not self.show_overlay
        elif key == pygame.K_w:
            self._move_waypoint(0.0, -25.0)
        elif key == pygame.K_s:
            self._move_waypoint(0.0, 25.0)
        elif key == pygame.K_a:
            self._move_waypoint(-25.0, 0.0)
        elif key == pygame.K_d:
            self._move_waypoint(25.0, 0.0)
        elif key == pygame.K_1:
            self._set_formation("v")
        elif key == pygame.K_2:
            self._set_formation("grid")
        elif key == pygame.K_3:
            self._set_formation("circle")
        elif key in (pygame.K_PLUS, pygame.K_EQUALS):
            self._set_flocking(max_speed=self.flocking.max_speed + 0.5)
        elif key in (pygame.K_MINUS, pygame.K_UNDERSCORE):
            self._set_flocking(max_speed=max(1.0, self.flocking.max_speed - 0.5))

    def _move_waypoint(self, dx: float, dy: float) -> None:
        """Move the local target and ask the leader to replicate it."""
        self.waypoint = Vector2D(
            min(max(self.waypoint.x + dx, 0.0), WORLD_WIDTH),
            min(max(self.waypoint.y + dy, 0.0), WORLD_HEIGHT),
        )
        self._send_control(
            {
                "type": "control",
                "command": "set_waypoint",
                "x": self.waypoint.x,
                "y": self.waypoint.y,
            },
            leader_only=True,
        )

    def _set_formation(self, shape: str) -> None:
        """Set formation shape through the current leader."""
        self.formation_shape = shape
        self._send_control(
            {"type": "control", "command": "set_formation", "shape": shape},
            leader_only=True,
        )

    def _set_flocking(self, **changes: float) -> None:
        """Update local flocking controls and broadcast to all drones."""
        values = {
            "neighbor_radius": self.flocking.neighbor_radius,
            "min_sep_dist": self.flocking.min_sep_dist,
            "max_speed": self.flocking.max_speed,
            "w_sep": self.flocking.w_sep,
            "w_ali": self.flocking.w_ali,
            "w_coh": self.flocking.w_coh,
            "w_way": self.flocking.w_way,
        }
        values.update(changes)
        self.flocking = FlockingConfig(**values)
        self._send_control(
            {"type": "control", "command": "set_flocking", **values},
            leader_only=False,
        )

    def _send_control(self, msg: dict[str, Any], leader_only: bool) -> None:
        """Send a control message to the leader or every drone."""
        targets = [self._leader_id()] if leader_only and self._leader_id() is not None else []
        if not targets:
            targets = list(range(self.n_total))
        payload = encode(msg)
        for drone_id in targets:
            try:
                self._push[drone_id].send(payload, zmq.NOBLOCK)
            except zmq.ZMQError:
                pass

    def _leader_id(self) -> int | None:
        """Return the current leader ID from snapshots, if known."""
        for snapshot in self.snapshots.values():
            if snapshot.raft_state == "leader":
                return snapshot.drone_id
        return None

    def _draw(self) -> None:
        """Render the full scene."""
        self.screen.fill(BACKGROUND)
        self._draw_grid()
        if self.show_overlay:
            self._draw_formation_overlay()
            self._draw_convex_hull()
        self._draw_waypoint()
        self._draw_drones()
        self._draw_panel()
        pygame.display.flip()

    def _draw_grid(self) -> None:
        for x in range(0, WORLD_WIDTH, 50):
            pygame.draw.line(self.screen, GRID, (x, 0), (x, WORLD_HEIGHT), 1)
        for y in range(0, WORLD_HEIGHT, 50):
            pygame.draw.line(self.screen, GRID, (0, y), (WORLD_WIDTH, y), 1)
        pygame.draw.line(self.screen, PANEL, (WORLD_WIDTH, 0), (WORLD_WIDTH, WORLD_HEIGHT), 2)

    def _draw_waypoint(self) -> None:
        point = (round(self.waypoint.x), round(self.waypoint.y))
        pygame.draw.circle(self.screen, TARGET, point, 8, 2)
        pygame.draw.line(self.screen, TARGET, (point[0] - 12, point[1]), (point[0] + 12, point[1]), 2)
        pygame.draw.line(self.screen, TARGET, (point[0], point[1] - 12), (point[0], point[1] + 12), 2)

    def _draw_formation_overlay(self) -> None:
        for drone_id in range(self.n_total):
            target = formation_target(
                self.waypoint,
                drone_id,
                self.n_total,
                self.formation_shape,
            )
            pygame.draw.circle(
                self.screen,
                FORMATION,
                (round(target.x), round(target.y)),
                5,
                1,
            )

    def _draw_drones(self) -> None:
        now = time.time()
        for snapshot in self.snapshots.values():
            stale = now - snapshot.last_seen > STALE_AFTER_SECONDS
            color = self._drone_color(snapshot, stale)
            pos = (round(snapshot.x), round(snapshot.y))
            pygame.draw.circle(self.screen, color, pos, 10)
            if snapshot.raft_state == "leader":
                pygame.draw.circle(self.screen, LEADER, pos, 15, 2)
                self._draw_text("L", (pos[0] - 4, pos[1] - 31), LEADER, self.small_font)

            self._draw_velocity(snapshot, color)
            if self.show_labels:
                label = f"{snapshot.drone_id} {snapshot.battery:.0f}%"
                self._draw_text(label, (pos[0] + 13, pos[1] - 10), TEXT, self.small_font)

    def _draw_velocity(self, snapshot: DroneSnapshot, color: tuple[int, int, int]) -> None:
        start = (round(snapshot.x), round(snapshot.y))
        end = (
            round(snapshot.x + snapshot.vx * 8),
            round(snapshot.y + snapshot.vy * 8),
        )
        pygame.draw.line(self.screen, color, start, end, 2)

    def _draw_convex_hull(self) -> None:
        points = [(snapshot.x, snapshot.y) for snapshot in self.snapshots.values()]
        hull = convex_hull(points)
        if len(hull) >= 3:
            pygame.draw.lines(
                self.screen,
                (71, 85, 105),
                True,
                [(round(x), round(y)) for x, y in hull],
                1,
            )

    def _draw_panel(self) -> None:
        panel_rect = pygame.Rect(WORLD_WIDTH, 0, PANEL_WIDTH, WORLD_HEIGHT)
        pygame.draw.rect(self.screen, PANEL, panel_rect)
        leader = self._leader_id()
        live = len(self.snapshots)
        self._draw_text("SwarmNet", (WORLD_WIDTH + 18, 18), TEXT, self.font)
        self._draw_text(f"leader: {leader if leader is not None else '?'}", (WORLD_WIDTH + 18, 50), MUTED, self.font)
        self._draw_text(f"nodes: {live}/{self.n_total}", (WORLD_WIDTH + 18, 75), MUTED, self.font)
        self._draw_text(f"formation: {self.formation_shape}", (WORLD_WIDTH + 18, 100), MUTED, self.font)
        self._draw_sliders()

    def _draw_sliders(self) -> None:
        sliders = self._slider_specs()
        y = 150
        for key, label, min_value, max_value in sliders:
            value = getattr(self.flocking, key)
            self._draw_text(f"{label}: {value:.2f}", (WORLD_WIDTH + 18, y - 22), TEXT, self.small_font)
            x0 = WORLD_WIDTH + 18
            x1 = WORLD_WIDTH + PANEL_WIDTH - 24
            pygame.draw.line(self.screen, GRID, (x0, y), (x1, y), 4)
            ratio = (value - min_value) / (max_value - min_value)
            knob_x = round(x0 + min(max(ratio, 0.0), 1.0) * (x1 - x0))
            pygame.draw.circle(self.screen, TARGET if key == self.active_slider else TEXT, (knob_x, y), 7)
            y += 56

    def _draw_text(
        self,
        text: str,
        position: tuple[int, int],
        color: tuple[int, int, int],
        font: pygame.font.Font,
    ) -> None:
        surface = font.render(text, True, color)
        self.screen.blit(surface, position)

    def _slider_specs(self) -> list[tuple[str, str, float, float]]:
        return [
            ("w_sep", "Separation", 0.0, 4.0),
            ("w_ali", "Alignment", 0.0, 4.0),
            ("w_coh", "Cohesion", 0.0, 4.0),
            ("w_way", "Waypoint", 0.0, 5.0),
            ("max_speed", "Speed", 1.0, 10.0),
        ]

    def _slider_at(self, pos: tuple[int, int]) -> str | None:
        x, y = pos
        if x < WORLD_WIDTH:
            return None
        slider_y = 150
        for key, _, _, _ in self._slider_specs():
            if abs(y - slider_y) <= 14:
                return key
            slider_y += 56
        return None

    def _update_slider(self, key: str, mouse_x: int) -> None:
        for slider_key, _, min_value, max_value in self._slider_specs():
            if slider_key != key:
                continue
            x0 = WORLD_WIDTH + 18
            x1 = WORLD_WIDTH + PANEL_WIDTH - 24
            ratio = min(max((mouse_x - x0) / (x1 - x0), 0.0), 1.0)
            self._set_flocking(**{key: min_value + ratio * (max_value - min_value)})

    def _drone_color(
        self,
        snapshot: DroneSnapshot,
        stale: bool,
    ) -> tuple[int, int, int]:
        if stale:
            return MUTED
        if snapshot.raft_state == "leader":
            return LEADER
        if snapshot.raft_state == "candidate":
            return CANDIDATE
        return FOLLOWER

    def close(self) -> None:
        """Close sockets and Pygame resources."""
        for socket in self._subscribers:
            socket.close(linger=0)
        for socket in self._push.values():
            socket.close(linger=0)
        self._ctx.term()
        pygame.quit()


def convex_hull(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Return convex hull points using the monotonic chain algorithm."""
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique

    def cross(
        origin: tuple[float, float],
        a: tuple[float, float],
        b: tuple[float, float],
    ) -> float:
        return (a[0] - origin[0]) * (b[1] - origin[1]) - (
            a[1] - origin[1]
        ) * (b[0] - origin[0])

    lower: list[tuple[float, float]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)

    upper: list[tuple[float, float]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)

    return lower[:-1] + upper[:-1]


def parse_args() -> argparse.Namespace:
    """Parse visualizer CLI arguments."""
    parser = argparse.ArgumentParser(description="SwarmNet Pygame visualizer")
    parser.add_argument("--n", type=int, required=True, help="Drone count")
    parser.add_argument("--base-port", type=int, default=BASE_PORT, help="Base port")
    parser.add_argument("--fps", type=int, default=FPS, help="Render FPS")
    return parser.parse_args()


def main() -> None:
    """CLI entry point."""
    args = parse_args()
    PygameVisualizer(args.n, args.base_port, args.fps).run()


if __name__ == "__main__":
    main()
