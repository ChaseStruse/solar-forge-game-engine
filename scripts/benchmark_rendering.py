"""Offscreen native geometry/sprite fixture; not a compositor/GPU benchmark."""

import argparse
import json
import platform
import statistics
import time

from PySide6 import __version__ as qt_version
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene
from render_fixture import moving_scene

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
scene = moving_scene(args.unique_textures if args.sprites else 0)
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
            "unique_textures": args.unique_textures if args.sprites else 0,
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
