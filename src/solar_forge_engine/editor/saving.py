"""Background scene publication with observed external-edit protection."""

import hashlib
from pathlib import Path

from PySide6.QtCore import QThread

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.project.assets import load_project_scene, save_project_scene
from solar_forge_engine.project.storage import (
    PublicationBusy,
    load_scene,
    read_scene_bytes,
    save_scene,
)


class SceneSaver(QThread):
    def __init__(self, path: Path, scene: Scene, root: Path | None, baseline: Scene | None) -> None:
        super().__init__()
        self.path, self.scene, self.root, self.baseline = path, scene, root, baseline
        self.error: str | None = None

    def run(self) -> None:
        try:
            previous = read_scene_bytes(self.path)
            if self.baseline is not None:
                if previous is None:
                    raise ValueError(
                        "The saved scene was removed externally. Use Save As or reopen it."
                    )
                current = (
                    load_project_scene(self.root, self.path) if self.root else load_scene(self.path)
                )
                if current != self.baseline:
                    raise ValueError(
                        "The saved scene changed externally. Use Save As or reopen it."
                    )
            fingerprint = hashlib.sha256(previous).hexdigest() if previous is not None else None
            for attempt in range(25):
                try:
                    self._publish(previous is None, fingerprint)
                    break
                except PublicationBusy:
                    if attempt == 24:
                        raise
                    self.msleep(20)
        except (OSError, ValueError) as error:
            self.error = str(error)

    def _publish(self, exclusive: bool, fingerprint: str | None) -> None:
        if self.root:
            save_project_scene(
                self.root,
                self.path,
                self.scene,
                exclusive=exclusive,
                expected_fingerprint=fingerprint,
            )
        else:
            save_scene(
                self.path,
                self.scene,
                exclusive=exclusive,
                expected_fingerprint=fingerprint,
            )
