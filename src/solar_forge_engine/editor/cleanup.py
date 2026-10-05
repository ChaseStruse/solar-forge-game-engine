"""Background cleanup scan and revalidated quarantine operation."""

from pathlib import Path

from PySide6.QtCore import QThread

from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.project.cleanup import CleanupPlan, plan_cleanup, quarantine_assets
from solar_forge_engine.project.workspace import Project


class CleanupWorker(QThread):
    def __init__(
        self, project: Project, protected: set[Sprite], plan: CleanupPlan | None = None
    ) -> None:
        super().__init__()
        self.project = project
        self.protected = protected
        self.plan = plan
        self.destination: Path | None = None
        self.error: str | None = None

    def run(self) -> None:
        try:
            if self.plan is None:
                self.plan = plan_cleanup(self.project, self.protected)
            else:
                self.destination = quarantine_assets(self.project, self.protected, self.plan)
        except (OSError, ValueError, RecursionError) as error:
            self.error = str(error)
