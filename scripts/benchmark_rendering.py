"""Offscreen native rectangle fixture; not a compositor/GPU or sprite benchmark."""

import json
import platform
import statistics
import time

from PySide6 import __version__ as qt_version
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QGraphicsScene

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.runtime.rendering import render_scene

app = QApplication([])
scene = Scene(
    entities=tuple(
        Entity(f"rect-{index}", x=(index % 40) * 24, y=(index // 40) * 20, width=16, height=16)
        for index in range(1000)
    )
)
canvas = QGraphicsScene()
canvas.setSceneRect(0, 0, 1024, 576)
items = render_scene(canvas, scene)
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
print(
    json.dumps(
        {
            "fixture": "1000 moving native rectangles, 1024x576 QImage",
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
