"""Offscreen native geometry/sprite fixture; not a compositor/GPU benchmark."""

import argparse
import base64
import json
import platform
import statistics
import time

from PySide6 import __version__ as qt_version
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.runtime.rendering import render_scene

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sprites", action="store_true", help="Use a shared transparent RGBA texture")
parser.add_argument(
    "--unique-textures", type=int, default=1, help="Sprite textures, from 1 to 1000"
)
args = parser.parse_args()
if not 1 <= args.unique_textures <= 1000 or (not args.sprites and args.unique_textures != 1):
    parser.error("--unique-textures requires --sprites and a count from 1 to 1000")
app = QApplication([])
sprites: list[Sprite] = []
if args.sprites:
    texture = QImage(16, 16, QImage.Format.Format_RGBA8888)
    texture.fill(QColor("#f4b544"))
    for x in range(16):
        for y in range(16):
            if (x // 4 + y // 4) % 2:
                texture.setPixelColor(x, y, QColor(34, 180, 170, 128))
    for index in range(args.unique_textures):
        variant = texture.copy()
        if index:
            variant.setPixelColor(0, 0, QColor(index % 256, index // 256, 170, 255))
        sprites.append(Sprite(16, 16, base64.b64encode(bytes(variant.constBits())).decode("ascii")))
scene = Scene(
    entities=tuple(
        Entity(
            f"rect-{index}",
            x=(index % 40) * 24,
            y=(index // 40) * 20,
            width=16,
            height=16,
            sprite=sprites[index % len(sprites)] if sprites else None,
        )
        for index in range(1000)
    )
)
canvas = QGraphicsScene()
canvas.setSceneRect(0, 0, 1024, 576)
construction_started = time.perf_counter()
items = render_scene(canvas, scene)
construction_ms = (time.perf_counter() - construction_started) * 1000
image = QImage(1024, 576, QImage.Format.Format_ARGB32_Premultiplied)
samples = []
for frame in range(130):
    started = time.perf_counter()
    for entity in scene.entities:
        items[entity.id].setPos(entity.x + frame % 8, entity.y)
    image.fill(QColor("#15181e"))
    painter = QPainter(image)
    canvas.render(painter)
    painter.end()
    if frame >= 10:
        samples.append((time.perf_counter() - started) * 1000)
ordered = sorted(samples)
kind = "sprites" if args.sprites else "rectangles"
print(
    json.dumps(
        {
            "fixture": f"1000 moving native {kind}, 1024x576 QImage",
            "unique_textures": len(set(sprites)),
            "construction_ms": round(construction_ms, 3),
            "warmup_frames": 10,
            "measured_frames": len(samples),
            "python": platform.python_version(),
            "qt": qt_version,
            "platform": platform.platform(),
            "qpa": app.platformName(),
            "median_ms": round(statistics.median(samples), 3),
            "p95_ms": round(ordered[int(len(ordered) * 0.95) - 1], 3),
        },
        indent=2,
    )
)
