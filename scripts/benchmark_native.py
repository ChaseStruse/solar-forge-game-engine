"""Native Qt paint cadence and synthetic viewport input; not compositor/hardware latency."""

import argparse
import json
import math
import platform
import statistics
import time

from PySide6 import __version__ as qt_version
from PySide6.QtCore import QEvent, QPointF, Qt, QTimer
from PySide6.QtGui import QMouseEvent, QPaintEvent
from PySide6.QtWidgets import QApplication, QGraphicsScene
from render_fixture import moving_scene

from solar_forge_engine.editor.viewport import SceneView
from solar_forge_engine.runtime.rendering import render_scene


def metrics(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "median_ms": round(statistics.median(samples), 3),
        "p95_ms": round(ordered[math.ceil(len(samples) * 0.95) - 1], 3),
        "max_ms": round(max(samples), 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--unique-textures", type=int, default=1000, help="Textures, from 1 to 1000"
    )
    parser.add_argument("--moving-items", type=int, default=1000, help="Moving objects, 1 to 1000")
    parser.add_argument("--scene-index", choices=("bsp", "none"), default="bsp")
    parser.add_argument(
        "--viewport-update", choices=("minimal", "bounding", "smart", "full"), default="minimal"
    )
    parser.add_argument(
        "--force-repaint", action="store_true", help="Repaint the full viewport each update"
    )
    args = parser.parse_args()
    if not 1 <= args.unique_textures <= 1000:
        parser.error("--unique-textures must be from 1 to 1000")
    if not 1 <= args.moving_items <= 1000:
        parser.error("--moving-items must be from 1 to 1000")
    app = QApplication([])
    app.setStyle("Fusion")
    scene = moving_scene(args.unique_textures)
    canvas = QGraphicsScene()
    canvas.setItemIndexMethod(
        QGraphicsScene.ItemIndexMethod.NoIndex
        if args.scene_index == "none"
        else QGraphicsScene.ItemIndexMethod.BspTreeIndex
    )
    canvas.setSceneRect(0, 0, 1024, 576)
    items = render_scene(canvas, scene, selectable=True)
    paints: list[float] = []
    cadence: list[float] = []
    update_to_paint: list[float] = []
    update_cpu: list[float] = []
    paint_queue_delay: list[float] = []
    input_to_selection: list[float] = []
    input_to_paint: list[float] = []
    updates = paint_count = input_count = 0
    frame_started: float | None = None
    update_finished: float | None = None
    previous_paint: float | None = None
    input_started: float | None = None
    expected_id: str | None = None
    selection_seen = complete = False

    class BenchView(SceneView):
        def paintEvent(self, event: QPaintEvent) -> None:
            nonlocal frame_started, previous_paint, paint_count, input_started, input_count
            started = time.perf_counter()
            super().paintEvent(event)
            finished = time.perf_counter()
            if frame_started is not None:
                paint_count += 1
                if paint_count > 10:
                    paints.append((finished - started) * 1000)
                    update_to_paint.append((finished - frame_started) * 1000)
                    assert previous_paint is not None
                    cadence.append((finished - previous_paint) * 1000)
                    assert update_finished is not None
                    paint_queue_delay.append((started - update_finished) * 1000)
                previous_paint = finished
                frame_started = None
                if paint_count == 130:
                    timer.stop()
                    QTimer.singleShot(50, post_input)
            elif input_started is not None and selection_seen:
                input_count += 1
                if input_count > 5:
                    input_to_paint.append((finished - input_started) * 1000)
                input_started = None
                QTimer.singleShot(10, post_input if input_count < 55 else finish)

    view = BenchView()
    view.setViewportUpdateMode(
        {
            "minimal": SceneView.ViewportUpdateMode.MinimalViewportUpdate,
            "bounding": SceneView.ViewportUpdateMode.BoundingRectViewportUpdate,
            "smart": SceneView.ViewportUpdateMode.SmartViewportUpdate,
            "full": SceneView.ViewportUpdateMode.FullViewportUpdate,
        }[args.viewport_update]
    )
    view.setScene(canvas)
    view.setSceneRect(canvas.sceneRect())
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setWindowTitle("Solar Forge native benchmark · temporary fixture")
    view.resize(1040, 620)

    def update() -> None:
        nonlocal updates, frame_started, update_finished
        started = time.perf_counter()
        if frame_started is None:
            frame_started = time.perf_counter()
        updates += 1
        for entity in scene.entities[: args.moving_items]:
            items[entity.id].setPos(entity.x + updates % 8, entity.y)
        if args.force_repaint:
            view.viewport().update()
        update_finished = time.perf_counter()
        if paint_count >= 10:
            update_cpu.append((update_finished - started) * 1000)

    def selected() -> None:
        nonlocal selection_seen
        if input_started is None or selection_seen:
            return
        if any(item.data(0) == expected_id for item in canvas.selectedItems()):
            selection_seen = True
            if input_count >= 5:
                input_to_selection.append((time.perf_counter() - input_started) * 1000)
            if args.force_repaint:
                view.viewport().update()

    def post_input() -> None:
        nonlocal input_started, selection_seen, expected_id
        entity = scene.entities[(input_count * 17) % len(scene.entities)]
        expected_id = entity.id
        point = view.mapFromScene(items[entity.id].pos() + QPointF(8, 8))
        global_point = view.viewport().mapToGlobal(point)
        selection_seen = False
        input_started = time.perf_counter()
        for kind, buttons in (
            (QEvent.Type.MouseButtonPress, Qt.MouseButton.LeftButton),
            (QEvent.Type.MouseButtonRelease, Qt.MouseButton.NoButton),
        ):
            QApplication.postEvent(
                view.viewport(),
                QMouseEvent(
                    kind,
                    QPointF(point),
                    QPointF(global_point),
                    Qt.MouseButton.LeftButton,
                    buttons,
                    Qt.KeyboardModifier.NoModifier,
                ),
            )

    def finish() -> None:
        nonlocal complete
        complete = True
        screen = view.screen()
        print(
            json.dumps(
                {
                    "fixture": "1000 moving 16x16 sprites; SceneView; 1040x620 logical window",
                    "qpa": app.platformName(),
                    "python": platform.python_version(),
                    "qt": qt_version,
                    "platform": platform.platform(),
                    "unique_textures": args.unique_textures,
                    "moving_items": args.moving_items,
                    "scene_index": args.scene_index,
                    "viewport_update": args.viewport_update,
                    "forced_repaint": args.force_repaint,
                    "screen_refresh_hz": screen.refreshRate(),
                    "device_pixel_ratio": view.devicePixelRatioF(),
                    "actual_window_size": [view.width(), view.height()],
                    "actual_viewport_size": [view.viewport().width(), view.viewport().height()],
                    "timer_interval_ms": 16,
                    "warmup_paints": 10,
                    "measured_paints": len(paints),
                    "requested_updates": updates,
                    "coalesced_updates": updates - paint_count,
                    "paint_cpu": metrics(paints),
                    "update_cpu": metrics(update_cpu),
                    "latest_update_to_paint_start": metrics(paint_queue_delay),
                    "update_to_paint_completion": metrics(update_to_paint),
                    "paint_completion_interval": metrics(cadence),
                    "input": "Qt-posted mouse click; excludes hardware, compositor, Inspector",
                    "warmup_clicks": 5,
                    "measured_clicks": len(input_to_paint),
                    "event_to_selection": metrics(input_to_selection),
                    "event_to_paint_completion": metrics(input_to_paint),
                },
                indent=2,
            ),
            flush=True,
        )
        view.close()
        app.quit()

    canvas.selectionChanged.connect(selected)
    timer = QTimer()
    timer.setTimerType(Qt.TimerType.PreciseTimer)
    timer.setInterval(16)
    timer.timeout.connect(update)
    view.show()
    view.fit_workspace(canvas.sceneRect())
    QTimer.singleShot(100, timer.start)
    QTimer.singleShot(15000, app.quit)
    app.exec()
    if not complete:
        raise RuntimeError("Benchmark did not complete within 15 seconds; keep the window visible.")


if __name__ == "__main__":
    main()
