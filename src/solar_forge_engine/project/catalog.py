"""Bounded discovery of reusable sprites referenced by saved project scenes."""

from collections.abc import Callable
from dataclasses import replace

from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.project.workspace import Project, list_scenes, open_scene

MAX_INDEX_BYTES = 16 * 1024 * 1024
MAX_CATALOG_PIXELS = 4 * 1024 * 1024
MAX_CATALOG_SPRITES = 128


def index_sprites(
    project: Project, cancelled: Callable[[], bool]
) -> tuple[list[tuple[str, Sprite]], list[str]]:
    sprites: list[tuple[str, Sprite]] = []
    known: set[Sprite] = set()
    warnings: list[str] = []
    remaining = MAX_INDEX_BYTES
    pixel_bytes = 0
    for reference in list_scenes(project):
        if cancelled():
            break
        try:
            path = replace(project, scene=reference).scene_path()
            size = path.stat().st_size
            if size > remaining:
                warnings.append("Project asset scan reached its 16 MiB scene-data limit.")
                break
            remaining -= size
            _, scene = open_scene(project, reference)
            for entity in scene.entities:
                sprite = entity.sprite
                if sprite is None or sprite in known:
                    continue
                size = sprite.width * sprite.height * 4
                if len(sprites) >= MAX_CATALOG_SPRITES or pixel_bytes + size > MAX_CATALOG_PIXELS:
                    warnings.append("Project asset palette reached its 128 sprite / 4 MiB limit.")
                    return sprites, warnings
                known.add(sprite)
                sprites.append((entity.name, sprite))
                pixel_bytes += size
        except (OSError, ValueError) as error:
            warnings.append(f"Skipped {reference}: {error}")
    return sprites, warnings
