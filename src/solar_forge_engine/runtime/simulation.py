"""Deterministic keyboard movement, independent of Qt."""

import math

from solar_forge_engine.core.commands import SetEntity
from solar_forge_engine.core.scene import Entity, Role, Scene

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


class Simulation:
    def __init__(self, scene: Scene, controlled_id: str) -> None:
        self.scene = scene
        self.runtime_scene = scene
        self.message = ""
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

    def script_state(self, horizontal: int, vertical: int, elapsed: float) -> dict[str, object]:
        if len(self.runtime_scene.entities) > 256:
            raise ValueError("Scene scripting currently supports at most 256 objects.")
        objects = {
            entity.id: {
                "id": entity.id,
                "name": entity.name,
                "x": entity.x,
                "y": entity.y,
                "width": entity.width,
                "height": entity.height,
                "role": entity.role.value,
            }
            for entity in self.runtime_scene.entities
        }
        player = objects[self.controlled.id]
        player.update(x=self.x, y=self.y, speed=self.speed)
        return {
            "objects": objects,
            "player": player,
            "input": {"x": horizontal, "y": vertical},
            "collected": len(self.collected),
            "total_coins": len(self.coins),
            "time": elapsed,
        }

    def apply_script(self, commands: object) -> None:
        """Validate the whole response before changing runtime state, never authored data."""
        if not isinstance(commands, list) or len(commands) > 32:
            raise ValueError("Scripts support at most 32 commands per callback.")
        updated = self.runtime_scene
        message = self.message
        moved_player = changed_speed = False
        for command in commands:
            if not isinstance(command, dict):
                raise ValueError("Invalid script command.")
            if command.get("op") == "position" and set(command) == {"op", "id", "x", "y"}:
                entity_id = command["id"]
                if not isinstance(entity_id, str):
                    raise ValueError("Script object IDs must be strings.")
                updated = SetEntity(entity_id, {"x": command["x"], "y": command["y"]}).apply(
                    updated
                )
                moved_player |= entity_id == self.controlled.id
            elif command.get("op") == "speed" and set(command) == {"op", "value"}:
                updated = SetEntity(self.controlled.id, {"move_speed": command["value"]}).apply(
                    updated
                )
                changed_speed = True
            elif command.get("op") == "message" and set(command) == {"op", "value"}:
                value = command["value"]
                if (
                    not isinstance(value, str)
                    or len(value) > 200
                    or any(ord(c) < 32 for c in value)
                ):
                    raise ValueError("Game messages must be at most 200 plain-text characters.")
                message = value
            else:
                raise ValueError("Unsupported script command.")
        self.runtime_scene = updated
        self.message = message
        self.controlled = updated.entity(self.controlled.id)
        if moved_player:
            self.x = min(max(self.controlled.x, 0), max(0, WORLD_WIDTH - self.controlled.width))
            self.y = min(max(self.controlled.y, 0), max(0, WORLD_HEIGHT - self.controlled.height))
        if changed_speed:
            self.speed = self.controlled.move_speed
        self.walls = tuple(
            e for e in updated.entities if e.role == Role.WALL and e.id != self.controlled.id
        )
        self.coins = tuple(
            e for e in updated.entities if e.role == Role.COIN and e.id != self.controlled.id
        )

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
