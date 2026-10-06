"""Shared native application lifecycle for editor Play and exported games."""

import json
import signal
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from solar_forge_engine.core.scene import InputPreset, Scene
from solar_forge_engine.runtime.player import PlayerWindow


def run_scene(
    scene: Scene, controlled_id: str, *, exported: bool = False, smoke: bool = False
) -> int:
    app = QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    window = PlayerWindow(scene, controlled_id)
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

        def press() -> None:
            window.activateWindow()
            QApplication.postEvent(
                window, QKeyEvent(QKeyEvent.Type.KeyPress, key, Qt.KeyboardModifier.NoModifier)
            )

        def finish() -> None:
            print(
                json.dumps(
                    {
                        "scene": scene.name,
                        "objects": len(scene.entities),
                        "x": window.simulation.x,
                        "collected": len(window.simulation.collected),
                        "ticks": window._ticks,
                        "score": window.simulation.score,
                        "scripts_ready": bool(window.script_host and window.script_host.ready),
                        "script_failed": bool(window.script_host and window.script_host.failed),
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
        QTimer.singleShot(400, finish)
    else:
        print("Game ready" if exported else "Preview ready", flush=True)
    return app.exec()
