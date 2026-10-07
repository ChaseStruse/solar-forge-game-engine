"""Shared native application lifecycle for editor Play and exported games."""

import json
import signal
import sys
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from solar_forge_engine.core.scene import InputPreset, Scene
from solar_forge_engine.runtime.player import PlayerWindow


def run_scene(
    scene: Scene,
    controlled_id: str,
    *,
    exported: bool = False,
    smoke: bool = False,
    editor_events: bool = False,
) -> int:
    app = QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    window = PlayerWindow(scene, controlled_id)
    if editor_events:
        # Only the trusted player writes events to stdout. Worker logs use stderr.
        window.script_failed.connect(
            lambda message, line: print(
                json.dumps(
                    {"type": "script_error", "message": message[:1000], "line": line},
                    ensure_ascii=False,
                ),
                flush=True,
            )
        )
    if exported:
        window.setWindowTitle(scene.name)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: window.close())
    window.show()
    if smoke:
        key = (
            Qt.Key.Key_D
            if scene.entity(controlled_id).input_preset == InputPreset.WASD
            else Qt.Key.Key_Right
        )

        startup_deadline = time.monotonic() + 5

        def press() -> None:
            if scene.script and not window._script_ready:
                if not window._script_failed and time.monotonic() < startup_deadline:
                    QTimer.singleShot(25, press)
                    return
                finish()
                return
            window.activateWindow()
            QApplication.postEvent(
                window, QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            )
            if scene.script:
                QApplication.postEvent(
                    window,
                    QKeyEvent(
                        QKeyEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier
                    ),
                )
                QTimer.singleShot(
                    120,
                    lambda: QApplication.postEvent(
                        window,
                        QKeyEvent(
                            QKeyEvent.Type.KeyRelease,
                            Qt.Key.Key_Space,
                            Qt.KeyboardModifier.NoModifier,
                        ),
                    ),
                )
            QTimer.singleShot(320, finish)

        def finish() -> None:
            print(
                json.dumps(
                    {
                        "scene": scene.name,
                        "objects": len(scene.entities),
                        "x": window.simulation.x,
                        "collected": len(window.simulation.collected),
                        "ticks": window._ticks,
                        "script_ready": window._script_ready,
                        "script_failed": window._script_failed,
                        "script_message": window.simulation.message,
                        "player_speed": window.simulation.speed,
                        "scene_unchanged": window.simulation.scene == scene,
                        "editor_loaded": any(
                            name.startswith(
                                (
                                    "solar_forge_engine.editor",
                                    "solar_forge_engine.ai",
                                    "solar_forge_engine.project",
                                )
                            )
                            for name in sys.modules
                        ),
                        "runtime_from_archive": __file__.startswith(
                            str(Path(sys.argv[0]).resolve()) + "/"
                        ),
                    }
                ),
                flush=True,
            )
            window.close()

        QTimer.singleShot(80, press)
    else:
        print("Game ready" if exported else "Preview ready", flush=True)
    result = app.exec()
    if smoke and scene.script and (window._script_failed or not window._script_ready):
        return 1
    return result
