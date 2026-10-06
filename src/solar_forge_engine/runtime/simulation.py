"""Deterministic movement and behavior actions, separate from authored scene data."""

import math
from dataclasses import dataclass

from solar_forge_engine.core.scene import Entity, Role, Scene
from solar_forge_engine.runtime.script_protocol import ScriptResult

WORLD_WIDTH = 1024
WORLD_HEIGHT = 576
FIXED_STEP = 1 / 60


def controlled_entity(scene: Scene, preferred: str | None = None) -> str:
    if not scene.entities:
        raise ValueError("Add an object before playing or exporting the scene.")
    for entity in scene.entities:
        if entity.role == Role.PLAYER:
            return entity.id
    if preferred is not None:
        return scene.entity(preferred).id
    return scene.entities[0].id


@dataclass
class Body:
    id: str
    x: float
    y: float
    width: float
    height: float
    color: str
    role: Role
    rotation: float = 0.0
    visible: bool = True

    def overlaps(self, other: "Body") -> bool:
        return (
            self.x < other.x + other.width
            and self.x + self.width > other.x
            and self.y < other.y + other.height
            and self.y + self.height > other.y
        )


class Simulation:
    def __init__(self, scene: Scene, controlled_id: str) -> None:
        self.scene = scene
        self.controlled = scene.entity(controlled_id)
        self.speed = self.controlled.move_speed
        self.bodies = {
            e.id: Body(e.id, e.x, e.y, e.width, e.height, e.color, e.role) for e in scene.entities
        }
        self.walls = tuple(
            body
            for body in self.bodies.values()
            if body.role == Role.WALL and body.id != controlled_id
        )
        self.coins = tuple(
            body
            for body in self.bodies.values()
            if body.role == Role.COIN and body.id != controlled_id
        )
        self.collected: set[str] = set()
        self.score = 0
        self.events: list[dict[str, str]] = []
        self.changed: set[str] = set()
        self.x = min(max(self.controlled.x, 0), max(0, WORLD_WIDTH - self.controlled.width))
        self.y = min(max(self.controlled.y, 0), max(0, WORLD_HEIGHT - self.controlled.height))

    @property
    def x(self) -> float:
        return self.bodies[self.controlled.id].x

    @x.setter
    def x(self, value: float) -> None:
        self.bodies[self.controlled.id].x = value

    @property
    def y(self) -> float:
        return self.bodies[self.controlled.id].y

    @y.setter
    def y(self, value: float) -> None:
        self.bodies[self.controlled.id].y = value

    def _event(self, actor: str, kind: str, other: str) -> None:
        event = {"entity_id": actor, "kind": kind, "other": other}
        if len(self.events) < 128 and event not in self.events:
            self.events.append(event)

    def _collect(self) -> None:
        player = self.bodies[self.controlled.id]
        for coin in self.coins:
            if coin.id not in self.collected and player.overlaps(coin):
                self.collected.add(coin.id)
                self._event(player.id, "collect", coin.id)
                self._event(coin.id, "collect", player.id)

    def move(self, identity: str, dx: float, dy: float) -> None:
        """Swept axis-aligned wall collision; visual rotation does not alter hit boxes."""
        body = self.bodies[identity]
        for axis, distance, extent, cross, cross_extent, limit in (
            ("x", dx, "width", "y", "height", WORLD_WIDTH),
            ("y", dy, "height", "x", "width", WORLD_HEIGHT),
        ):
            origin = getattr(body, axis)
            size = getattr(body, extent)
            target = min(max(origin + distance, 0), max(0, limit - size))
            for wall in self.walls:
                if wall.id == identity or not (
                    getattr(body, cross) < getattr(wall, cross) + getattr(wall, cross_extent)
                    and getattr(body, cross) + getattr(body, cross_extent) > getattr(wall, cross)
                ):
                    continue
                boundary = getattr(wall, axis)
                candidate = target
                if distance > 0 and origin + size <= boundary:
                    candidate = min(target, max(origin, boundary - size))
                elif distance < 0 and origin >= boundary + getattr(wall, extent):
                    candidate = max(target, min(origin, boundary + getattr(wall, extent)))
                if candidate != target:
                    self._event(identity, "collision", wall.id)
                    self._event(wall.id, "collision", identity)
                target = candidate
            setattr(body, axis, target)
        self.changed.add(identity)

    def step(self, horizontal: int, vertical: int, dt: float = FIXED_STEP) -> None:
        if horizontal not in (-1, 0, 1) or vertical not in (-1, 0, 1):
            raise ValueError("Movement axes must be -1, 0 or 1.")
        if not math.isfinite(dt) or not 0 < dt <= 0.1:
            raise ValueError("Simulation step must be finite and within (0, 0.1].")
        length = math.hypot(horizontal, vertical)
        if length:
            distance = self.speed * dt / length
            self.move(self.controlled.id, horizontal * distance, vertical * distance)
        self._collect()

    def apply(self, result: ScriptResult) -> None:
        """Apply a fully validated worker packet to runtime state only."""
        if result.fault is not None:
            return
        for action in result.actions:
            body = self.bodies[action.entity_id]
            values = action.values
            if action.kind == "move":
                self.move(body.id, float(values[0]), float(values[1]))
            elif action.kind == "position":
                body.x = min(max(float(values[0]), 0), max(0, WORLD_WIDTH - body.width))
                body.y = min(max(float(values[1]), 0), max(0, WORLD_HEIGHT - body.height))
            elif action.kind == "rotation":
                body.rotation = float(values[0]) % 360
            elif action.kind == "color":
                body.color = str(values[0])
            elif action.kind == "visible":
                body.visible = bool(values[0])
            elif action.kind == "score":
                self.score = min(max(self.score + int(values[0]), -1_000_000), 1_000_000)
            self.changed.add(body.id)
        self._collect()

    def overlaps(self, entity: Entity | Body) -> bool:
        return self.bodies[self.controlled.id].overlaps(self.bodies[entity.id])

    @property
    def won(self) -> bool:
        return bool(self.coins) and len(self.collected) == len(self.coins)
