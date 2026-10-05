"""Validate project sprite references off the UI thread; create icons only in the UI."""

from PySide6.QtCore import QThread

from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.project.catalog import index_sprites
from solar_forge_engine.project.workspace import Project


class AssetIndexer(QThread):
    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.sprites: list[tuple[str, Sprite]] = []
        self.warnings: list[str] = []

    def run(self) -> None:
        try:
            self.sprites, self.warnings = index_sprites(self.project, self.isInterruptionRequested)
        except (OSError, ValueError) as error:
            self.warnings = [f"Project asset scan failed: {error}"]
