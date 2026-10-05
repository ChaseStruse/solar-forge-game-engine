"""Shared fixed-size moving-object fixture for software and native benchmarks."""

import base64

from PySide6.QtGui import QColor, QImage

from solar_forge_engine.core.animation import Animation
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.sprite import Sprite


def moving_scene(unique_textures: int = 0, animated_items: int = 0) -> Scene:
    if not 0 <= animated_items <= 1000 or (animated_items and not unique_textures):
        raise ValueError("Animated fixture requires sprites and 0–1000 animated objects.")
    sprites: list[Sprite] = []
    if unique_textures:
        texture = QImage(32 if animated_items else 16, 16, QImage.Format.Format_RGBA8888)
        texture.fill(QColor("#f4b544"))
        for x in range(texture.width()):
            for y in range(16):
                if (x // 4 + y // 4) % 2:
                    texture.setPixelColor(x, y, QColor(34, 180, 170, 128))
                elif x >= 16:
                    texture.setPixelColor(x, y, QColor("#69a75b"))
        for index in range(unique_textures):
            variant = texture.copy()
            if index:
                variant.setPixelColor(0, 0, QColor(index % 256, index // 256, 170, 255))
            sprites.append(
                Sprite(
                    texture.width(),
                    16,
                    base64.b64encode(bytes(variant.constBits())).decode("ascii"),
                )
            )
    return Scene(
        entities=tuple(
            Entity(
                f"rect-{index}",
                x=(index % 40) * 24,
                y=(index // 40) * 20,
                width=16,
                height=16,
                sprite=sprites[index % len(sprites)] if sprites else None,
                animation=Animation(columns=2, fps=60) if index < animated_items else None,
            )
            for index in range(1000)
        )
    )
