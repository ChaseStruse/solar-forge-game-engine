"""Actual PlayerWindow animation workload; Qt paint completion, not compositor presentation."""

import argparse
import json
import platform
import time
from dataclasses import replace

from benchmark_native import metrics
from PySide6 import __version__ as qt_version
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QPaintEvent
from PySide6.QtWidgets import QApplication
from render_fixture import moving_scene

from solar_forge_engine.core.scene import Role
from solar_forge_engine.runtime import player


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--animated-items", type=int, default=1000, help="Animated sprites, 0–1000")
    parser.add_argument("--unique-textures", type=int, default=1000, help="Sprite textures, 1–1000")
    parser.add_argument("--viewport-update", choices=("auto", "minimal", "full"), default="auto")
    args = parser.parse_args()
    if not 0 <= args.animated_items <= 1000 or not 1 <= args.unique_textures <= 1000:
        parser.error("Require 0–1000 animated items and 1–1000 textures")
    app = QApplication([])
    app.setStyle("Fusion")
    fixture = moving_scene(args.unique_textures, args.animated_items)
    scene = replace(
        fixture,
        entities=(
            replace(fixture.entities[0], role=Role.PLAYER, move_speed=60),
            *fixture.entities[1:],
        ),
    )
    paints, cadence, sync_cpu, queue_delay, sync_to_paint = [], [], [], [], []
    recording = complete = False
    paint_count = sync_count = 0
    last_painted_sync = 0
    sync_started = sync_finished = previous_paint = None
    latest_sync_cpu = 0.0
    first_frame = last_frame = None

    class TimedView(player.GameView):
        def paintEvent(self, event: QPaintEvent) -> None:
            nonlocal paint_count, previous_paint, last_painted_sync
            started = time.perf_counter()
            super().paintEvent(event)
            finished = time.perf_counter()
            if not recording or sync_started is None or sync_count == last_painted_sync:
                return
            last_painted_sync = sync_count
            paint_count += 1
            if paint_count > 10:
                assert previous_paint is not None and sync_finished is not None
                paints.append((finished - started) * 1000)
                cadence.append((finished - previous_paint) * 1000)
                sync_cpu.append(latest_sync_cpu)
                queue_delay.append((started - sync_finished) * 1000)
                sync_to_paint.append((finished - sync_started) * 1000)
            previous_paint = finished
            if paint_count == 130:
                window.timer.stop()
                QTimer.singleShot(0, finish)

    class TimedPlayer(player.PlayerWindow):
        def _sync_position(self) -> None:
            nonlocal \
                sync_count, \
                sync_started, \
                sync_finished, \
                latest_sync_cpu, \
                first_frame, \
                last_frame
            started = time.perf_counter()
            super()._sync_position()
            if args.viewport_update != "auto":
                self.view.setViewportUpdateMode(
                    TimedView.ViewportUpdateMode.FullViewportUpdate
                    if args.viewport_update == "full"
                    else TimedView.ViewportUpdateMode.MinimalViewportUpdate
                )
            if recording:
                sync_count += 1
                sync_started = started
                sync_finished = time.perf_counter()
                latest_sync_cpu = (sync_finished - started) * 1000
                if self.animator.entries:
                    pixmap = self.animator.entries[0][0].pixmap()
                    if first_frame is None:
                        first_frame = pixmap.cacheKey()
                    elif pixmap.cacheKey() != first_frame:
                        last_frame = pixmap.cacheKey()

    # Instrument the real Play view in this isolated benchmark process only.
    player.GameView = TimedView
    window = TimedPlayer(scene, "rect-0")
    window.show()

    def begin() -> None:
        nonlocal recording
        if not window.isActiveWindow():
            QTimer.singleShot(50, begin)
            return
        recording = True
        QApplication.postEvent(
            window, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_D, Qt.KeyboardModifier.NoModifier)
        )

    def finish() -> None:
        nonlocal complete
        if args.animated_items:
            assert last_frame is not None, "Expected animation frames to change during playback"
        assert window.simulation.x > scene.entities[0].x
        assert window.simulation.scene == scene
        complete = True
        print(
            json.dumps(
                {
                    "fixture": "PlayerWindow; 1000 sprites; one player; two-frame 60 fps sheets",
                    "animated_items": args.animated_items,
                    "unique_textures": args.unique_textures,
                    "viewport_update": args.viewport_update,
                    "qpa": app.platformName(),
                    "python": platform.python_version(),
                    "qt": qt_version,
                    "platform": platform.platform(),
                    "screen_refresh_hz": window.screen().refreshRate(),
                    "device_pixel_ratio": window.devicePixelRatioF(),
                    "actual_viewport_size": [
                        window.view.viewport().width(),
                        window.view.viewport().height(),
                    ],
                    "timer_interval_ms": window.timer.interval(),
                    "warmup_paints": 10,
                    "measured_paints": len(paints),
                    "sync_calls": sync_count,
                    "paint_cpu": metrics(paints),
                    "sync_cpu": metrics(sync_cpu),
                    "latest_sync_to_paint_start": metrics(queue_delay),
                    "sync_to_paint_completion": metrics(sync_to_paint),
                    "paint_completion_interval": metrics(cadence),
                    "animation_frames_changed": last_frame is not None,
                    "authored_scene_unchanged": window.simulation.scene == scene,
                },
                indent=2,
            ),
            flush=True,
        )
        window.close()
        app.quit()

    QTimer.singleShot(100, begin)
    QTimer.singleShot(15000, app.quit)
    app.exec()
    if not complete:
        raise RuntimeError("Play benchmark timed out; keep its window visible and focused.")


if __name__ == "__main__":
    main()
