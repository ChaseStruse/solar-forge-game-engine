"""Deterministic keyboard movement, independent of Qt."""

import math

from solar_forge_engine.core.scene import Scene

WORLD_WIDTH = 1024
WORLD_HEIGHT = 576
FIXED_STEP = 1 / 60


class Simulation:
    def __init__(self, scene: Scene, controlled_id: str) -> None:
        self.scene = scene
        self.controlled = scene.entity(controlled_id)
        self.speed = 240.0
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
            self.x = min(
                max(self.x + horizontal * distance, 0), max(0, WORLD_WIDTH - self.controlled.width)
            )
            self.y = min(
                max(self.y + vertical * distance, 0), max(0, WORLD_HEIGHT - self.controlled.height)
            )
