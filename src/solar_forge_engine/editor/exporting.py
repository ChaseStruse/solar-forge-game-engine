"""Build native exports outside the UI thread from an immutable applied snapshot."""

from pathlib import Path

from PySide6.QtCore import QThread

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project.exporting import export_game


class ExportWorker(QThread):
    def __init__(self, path: Path, scene: Scene) -> None:
        super().__init__()
        self.path, self.scene = path, scene
        self.size = 0
        self.error: str | None = None

    def run(self) -> None:
        try:
            self.size = export_game(self.path, self.scene)
        except (OSError, ValueError) as error:
            self.error = str(error)
