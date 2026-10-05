"""Validated commands shared by manual editing and future AI tools."""

from dataclasses import asdict, dataclass, replace
from typing import Protocol

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.sprite import Sprite


class Command(Protocol):
    def apply(self, scene: Scene) -> Scene: ...


@dataclass(frozen=True)
class CreateEntity:
    entity: Entity

    def apply(self, scene: Scene) -> Scene:
        return replace(scene, entities=(*scene.entities, self.entity))


@dataclass(frozen=True)
class SetEntity:
    """Replace editable entity properties without allowing its ID to change."""

    entity_id: str
    changes: dict[str, object]

    def apply(self, scene: Scene) -> Scene:
        if not set(self.changes) <= {
            "name",
            "x",
            "y",
            "width",
            "height",
            "color",
            "role",
            "sprite",
            "move_speed",
            "input_preset",
            "animation",
        }:
            raise ValueError("Only editable entity properties may be changed.")
        entity = Entity.from_data({**asdict(scene.entity(self.entity_id)), **self.changes})
        return replace(
            scene,
            entities=tuple(
                entity if item.id == self.entity_id else item for item in scene.entities
            ),
        )


@dataclass(frozen=True)
class DeleteEntity:
    entity_id: str

    def apply(self, scene: Scene) -> Scene:
        scene.entity(self.entity_id)
        return replace(scene, entities=tuple(e for e in scene.entities if e.id != self.entity_id))


@dataclass(frozen=True)
class RestoreScene:
    scene: Scene

    def apply(self, scene: Scene) -> Scene:
        return self.scene


class Document:
    """Atomic in-memory transactions with bounded history and monotonic revisions."""

    def __init__(self, scene: Scene | None = None) -> None:
        self._scene = scene if scene is not None else Scene()
        self._revision = 0
        self._undo: list[Scene] = []
        self._redo: list[Scene] = []

    @property
    def scene(self) -> Scene:
        return self._scene

    @property
    def revision(self) -> int:
        return self._revision

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def retained_sprites(self) -> set[Sprite]:
        return {
            entity.sprite
            for scene in (self._scene, *self._undo, *self._redo)
            for entity in scene.entities
            if entity.sprite is not None
        }

    def execute(self, *commands: Command, expected_revision: int) -> None:
        if expected_revision != self._revision:
            raise ValueError("The scene changed. Review the edit against its current revision.")
        candidate = self._scene
        for command in commands:
            candidate = command.apply(candidate)
        if candidate == self._scene:
            return
        self._undo.append(self._scene)
        self._undo = self._undo[-100:]
        self._redo.clear()
        self._scene = candidate
        self._revision += 1

    def undo(self) -> None:
        if self._undo:
            self._redo.append(self._scene)
            self._scene = self._undo.pop()
            self._revision += 1

    def redo(self) -> None:
        if self._redo:
            self._undo.append(self._scene)
            self._scene = self._redo.pop()
            self._revision += 1
