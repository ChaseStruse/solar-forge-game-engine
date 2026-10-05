"""Deterministic keyboard movement, independent of Qt."""

import math

from solar_forge_engine.core.scene import Entity, Role, Scene

WORLD_WIDTH = 1024
WORLD_HEIGHT = 576
FIXED_STEP = 1 / 60


class Simulation:
    def __init__(self, scene: Scene, controlled_id: str) -> None:
        self.scene = scene
        self.controlled = scene.entity(controlled_id)
        self.speed = self.controlled.move_speed
        self.walls = tuple(
            e for e in scene.entities if e.role == Role.WALL and e.id != controlled_id
        )
        self.coins = tuple(
            e for e in scene.entities if e.role == Role.COIN and e.id != controlled_id
        )
        self.collected: set[str] = set()
        self.x = min(max(self.controlled.x, 0), max(0, WORLD_WIDTH - self.controlled.width))
        self.y = min(max(self.controlled.y, 0), max(0, WORLD_HEIGHT - self.controlled.height))

    def step(self, horizontal: int, vertical: int, dt: float = FIXED_STEP) -> None:
        if horizontal not in (-1, 0, 1) or vertical not in (-1, 0, 1):
            raise ValueError("Movement axes must be -1, 0 or 1.")
        if not math.isfinite(dt) or not 0 < dt <= 0.1:
            raise ValueError("Simulation step must be finite and within (0, 0.1].")
        length = math.hypot(horizontal, vertical)
        if length:
            distance = self.speed * dt / length
            target_x = min(
                max(self.x + horizontal * distance, 0), max(0, WORLD_WIDTH - self.controlled.width)
            )
            for wall in self.walls:
                if self.y < wall.y + wall.height and self.y + self.controlled.height > wall.y:
                    if horizontal > 0 and self.x + self.controlled.width <= wall.x:
                        target_x = min(target_x, max(self.x, wall.x - self.controlled.width))
                    elif horizontal < 0 and self.x >= wall.x + wall.width:
                        target_x = max(target_x, min(self.x, wall.x + wall.width))
            self.x = target_x
            target_y = min(
                max(self.y + vertical * distance, 0), max(0, WORLD_HEIGHT - self.controlled.height)
            )
            for wall in self.walls:
                if self.x < wall.x + wall.width and self.x + self.controlled.width > wall.x:
                    if vertical > 0 and self.y + self.controlled.height <= wall.y:
                        target_y = min(target_y, max(self.y, wall.y - self.controlled.height))
                    elif vertical < 0 and self.y >= wall.y + wall.height:
                        target_y = max(target_y, min(self.y, wall.y + wall.height))
            self.y = target_y
        self.collected.update(coin.id for coin in self.coins if self.overlaps(coin))

    def overlaps(self, entity: Entity) -> bool:
        return (
            self.x < entity.x + entity.width
            and self.x + self.controlled.width > entity.x
            and self.y < entity.y + entity.height
            and self.y + self.controlled.height > entity.y
        )

    @property
    def won(self) -> bool:
        return bool(self.coins) and len(self.collected) == len(self.coins)
