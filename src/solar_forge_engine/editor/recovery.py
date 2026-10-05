"""Keep recovery serialization and filesystem writes off the Qt UI thread."""

from PySide6.QtCore import QThread

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project.recovery import clear_recovery, write_recovery
from solar_forge_engine.project.workspace import Project


class RecoveryWriter(QThread):
    def __init__(self, project: Project, scene: Scene, baseline: Scene) -> None:
        super().__init__()
        self.project = project
        self.scene = scene
        self.baseline = baseline
        self.error: str | None = None
        self.discard = False

    def run(self) -> None:
        try:
            write_recovery(self.project, self.scene, self.baseline)
        except (OSError, ValueError) as error:
            self.error = str(error)


class RecoveryCleaner(QThread):
    def __init__(self, project: Project, baseline: Scene | None) -> None:
        super().__init__()
        self.project = project
        self.baseline = baseline
        self.error: str | None = None

    def run(self) -> None:
        try:
            clear_recovery(self.project, self.baseline)
        except (OSError, ValueError) as error:
            self.error = str(error)
