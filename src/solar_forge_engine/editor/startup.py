"""Validate startup-scene assets and atomically update settings off the UI thread."""

from PySide6.QtCore import QThread

from solar_forge_engine.project.workspace import Project, set_startup_scene


class StartupWriter(QThread):
    def __init__(self, project: Project, reference: str, expected: Project) -> None:
        super().__init__()
        self.project = project
        self.reference = reference
        self.expected = expected
        self.result: Project | None = None
        self.error: str | None = None

    def run(self) -> None:
        try:
            self.result = set_startup_scene(self.project, self.reference, self.expected)
        except (OSError, ValueError, RecursionError) as error:
            self.error = str(error)
