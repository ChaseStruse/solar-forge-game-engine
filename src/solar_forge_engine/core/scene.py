"""Versioned scene documents. Loading never executes project code."""

import math
import re
from dataclasses import asdict, dataclass
from enum import StrEnum

FORMAT_VERSION = 2
MAX_ENTITIES = 10_000


class Role(StrEnum):
    DECORATION = "decoration"
    PLAYER = "player"
    WALL = "wall"
    COIN = "coin"


def text(value: object, label: str, limit: int = 100) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must contain 1–{limit} characters.")
    if any(ord(char) < 32 for char in value):
        raise ValueError(f"{label} must not contain control characters.")
    return value


def number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number.")
    if value < -100_000 or value > 100_000:
        raise ValueError(f"{label} must be finite and within ±100,000.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite and within ±100,000.")
    return result


@dataclass(frozen=True)
class Entity:
    id: str
    name: str = "Rectangle"
    x: float = 0
    y: float = 0
    width: float = 64
    height: float = 64
    color: str = "#f4b544"
    role: Role = Role.DECORATION

    def __post_init__(self) -> None:
        if not isinstance(self.role, Role):
            raise ValueError("Unknown entity role.")
        if not isinstance(self.id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.id):
            raise ValueError("Entity ID must contain 1–64 letters, digits, underscores or hyphens.")
        text(self.name, "Entity name")
        for field in ("x", "y", "width", "height"):
            number(getattr(self, field), field)
        if self.width <= 0 or self.height <= 0:
            raise ValueError("Width and height must be positive.")
        if not isinstance(self.color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", self.color):
            raise ValueError("Color must be a six-digit hex value such as #f4b544.")

    @classmethod
    def from_data(cls, value: object) -> "Entity":
        fields = {"id", "name", "x", "y", "width", "height", "color", "role"}
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError("Invalid entity fields.")
        return cls(
            id=text(value["id"], "Entity ID", 64),
            name=text(value["name"], "Entity name"),
            x=number(value["x"], "x"),
            y=number(value["y"], "y"),
            width=number(value["width"], "width"),
            height=number(value["height"], "height"),
            color=text(value["color"], "Color"),
            role=Role(text(value["role"], "Role")),
        )


@dataclass(frozen=True)
class Scene:
    name: str = "Untitled scene"
    entities: tuple[Entity, ...] = ()

    def __post_init__(self) -> None:
        text(self.name, "Scene name")
        if not isinstance(self.entities, tuple) or len(self.entities) > MAX_ENTITIES:
            raise ValueError(f"A scene supports at most {MAX_ENTITIES:,} entities.")
        if any(not isinstance(entity, Entity) for entity in self.entities):
            raise ValueError("Scene entries must be entities.")
        if len({entity.id for entity in self.entities}) != len(self.entities):
            raise ValueError("Entity IDs must be unique.")

    def entity(self, entity_id: str) -> Entity:
        for entity in self.entities:
            if entity.id == entity_id:
                return entity
        raise ValueError(f"Entity {entity_id!r} no longer exists.")

    def to_data(self) -> dict[str, object]:
        return {
            "format_version": FORMAT_VERSION,
            "name": self.name,
            "entities": [asdict(entity) for entity in self.entities],
        }

    @classmethod
    def from_data(cls, value: object) -> "Scene":
        if not isinstance(value, dict) or set(value) != {"format_version", "name", "entities"}:
            raise ValueError("Invalid scene document fields.")
        version = value["format_version"]
        if type(version) is not int or version not in (1, FORMAT_VERSION):
            raise ValueError(
                "Unsupported scene format version; this editor supports versions 1 and 2."
            )
        entries = value["entities"]
        if not isinstance(entries, list) or len(entries) > MAX_ENTITIES:
            raise ValueError("Invalid entity list or scene size exceeds the limit.")
        if version == 1:
            if any(not isinstance(entry, dict) or "role" in entry for entry in entries):
                raise ValueError("Invalid version-one entity fields.")
            entries = [{**entry, "role": "decoration"} for entry in entries]
        entities = [Entity.from_data(entry) for entry in entries]
        return cls(name=text(value["name"], "Scene name"), entities=tuple(entities))
