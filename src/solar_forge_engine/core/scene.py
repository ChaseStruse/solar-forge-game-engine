"""Versioned scene documents. Loading never executes project code."""

import math
import re
from dataclasses import asdict, dataclass
from enum import StrEnum

from solar_forge_engine.core.animation import Animation
from solar_forge_engine.core.audio import SoundClip
from solar_forge_engine.core.script import MAX_SCRIPT_TOTAL_BYTES, MAX_SCRIPTS, ScriptBinding
from solar_forge_engine.core.sprite import Sprite

FORMAT_VERSION = 11
MAX_ENTITIES = 10_000


class Role(StrEnum):
    DECORATION = "decoration"
    PLAYER = "player"
    WALL = "wall"
    COIN = "coin"


class InputPreset(StrEnum):
    BOTH = "wasd_arrows"
    WASD = "wasd"
    ARROWS = "arrows"


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
    sprite: Sprite | None = None
    move_speed: float = 240
    input_preset: InputPreset = InputPreset.BOTH
    animation: Animation | None = None

    def __post_init__(self) -> None:
        if not 0 <= number(self.move_speed, "Movement speed") <= 2000:
            raise ValueError("Movement speed must be within 0–2,000 units/second.")
        if not isinstance(self.input_preset, InputPreset):
            raise ValueError("Unknown input preset.")
        if self.sprite is not None and not isinstance(self.sprite, Sprite):
            raise ValueError("Invalid sprite data.")
        if self.animation is not None:
            if not isinstance(self.animation, Animation) or self.sprite is None:
                raise ValueError("Animation requires a sprite and valid animation settings.")
            if (
                self.sprite.width % self.animation.columns
                or self.sprite.height % self.animation.rows
            ):
                raise ValueError("Sprite dimensions must divide evenly into the animation grid.")
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
        fields = {
            "id",
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
        }
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError("Invalid entity fields.")
        return cls(
            animation=Animation.from_data(value["animation"])
            if value["animation"] is not None
            else None,
            move_speed=number(value["move_speed"], "Movement speed"),
            input_preset=InputPreset(text(value["input_preset"], "Input preset")),
            id=text(value["id"], "Entity ID", 64),
            name=text(value["name"], "Entity name"),
            x=number(value["x"], "x"),
            y=number(value["y"], "y"),
            width=number(value["width"], "width"),
            height=number(value["height"], "height"),
            color=text(value["color"], "Color"),
            role=Role(text(value["role"], "Role")),
            sprite=Sprite.from_data(value["sprite"]) if value["sprite"] is not None else None,
        )


@dataclass(frozen=True)
class Scene:
    name: str = "Untitled scene"
    entities: tuple[Entity, ...] = ()
    coin_sound: SoundClip | None = None
    scripts: tuple[ScriptBinding, ...] = ()

    def __post_init__(self) -> None:
        text(self.name, "Scene name")
        if self.coin_sound is not None and not isinstance(self.coin_sound, SoundClip):
            raise ValueError("Invalid coin-collection sound.")
        if not isinstance(self.entities, tuple) or len(self.entities) > MAX_ENTITIES:
            raise ValueError(f"A scene supports at most {MAX_ENTITIES:,} entities.")
        if any(not isinstance(entity, Entity) for entity in self.entities):
            raise ValueError("Scene entries must be entities.")
        if len({entity.id for entity in self.entities}) != len(self.entities):
            raise ValueError("Entity IDs must be unique.")
        if not isinstance(self.scripts, tuple) or len(self.scripts) > MAX_SCRIPTS:
            raise ValueError("A scene supports at most 16 Python behaviors.")
        if any(not isinstance(script, ScriptBinding) for script in self.scripts):
            raise ValueError("Invalid Python behavior binding.")
        identities = {entity.id for entity in self.entities}
        if len({script.entity_id for script in self.scripts}) != len(self.scripts):
            raise ValueError("Attach at most one Python behavior to each object.")
        if any(script.entity_id not in identities for script in self.scripts):
            raise ValueError("Python behaviors must attach to existing objects.")
        if (
            sum(len(script.source.encode("utf-8")) for script in self.scripts)
            > MAX_SCRIPT_TOTAL_BYTES
        ):
            raise ValueError("Scene Python source must be no larger than 512 KiB.")

    def entity(self, entity_id: str) -> Entity:
        for entity in self.entities:
            if entity.id == entity_id:
                return entity
        raise ValueError(f"Entity {entity_id!r} no longer exists.")

    def to_data(self) -> dict[str, object]:
        return {
            "format_version": FORMAT_VERSION,
            "name": self.name,
            "coin_sound": asdict(self.coin_sound) if self.coin_sound else None,
            "entities": [asdict(entity) for entity in self.entities],
            "scripts": [asdict(script) for script in self.scripts],
        }

    @classmethod
    def from_data(cls, value: object) -> "Scene":
        if not isinstance(value, dict):
            raise ValueError("Invalid scene document fields.")
        fields = {"format_version", "name", "entities"}
        if value.get("format_version") in (9, FORMAT_VERSION):
            fields.add("coin_sound")
        if value.get("format_version") == FORMAT_VERSION:
            fields.add("scripts")
        if set(value) != fields:
            raise ValueError("Invalid scene document fields.")
        version = value["format_version"]
        if type(version) is not int or version not in (1, 2, 3, 5, 7, 9, FORMAT_VERSION):
            raise ValueError(
                "Unsupported scene format version; supported versions: 1, 2, 3, 5, 7, 9 and 11."
            )
        entries = value["entities"]
        if not isinstance(entries, list) or len(entries) > MAX_ENTITIES:
            raise ValueError("Invalid entity list or scene size exceeds the limit.")
        if version == 1:
            if any(not isinstance(entry, dict) or "role" in entry for entry in entries):
                raise ValueError("Invalid version-one entity fields.")
            entries = [{**entry, "role": "decoration"} for entry in entries]
        if version in (1, 2):
            if any(not isinstance(entry, dict) or "sprite" in entry for entry in entries):
                raise ValueError("Invalid legacy entity fields.")
            entries = [{**entry, "sprite": None} for entry in entries]
        if version in (1, 2, 3):
            if any(
                not isinstance(entry, dict) or {"move_speed", "input_preset"} & set(entry)
                for entry in entries
            ):
                raise ValueError("Invalid legacy movement fields.")
            entries = [
                {**entry, "move_speed": 240, "input_preset": "wasd_arrows"} for entry in entries
            ]
        if version in (1, 2, 3, 5):
            if any(not isinstance(entry, dict) or "animation" in entry for entry in entries):
                raise ValueError("Invalid legacy animation fields.")
            entries = [{**entry, "animation": None} for entry in entries]
        entities = [Entity.from_data(entry) for entry in entries]
        scripts = value.get("scripts", [])
        if not isinstance(scripts, list) or len(scripts) > MAX_SCRIPTS:
            raise ValueError("Invalid Python behavior list.")
        return cls(
            name=text(value["name"], "Scene name"),
            entities=tuple(entities),
            coin_sound=SoundClip.from_data(value["coin_sound"])
            if version in (9, FORMAT_VERSION) and value["coin_sound"] is not None
            else None,
            scripts=tuple(ScriptBinding.from_data(script) for script in scripts),
        )
