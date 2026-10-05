"""Native quarantine browser with worker-based scanning and restoration."""

from PySide6.QtCore import QThread
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QLabel, QListWidget, QPushButton, QVBoxLayout, QWidget

from solar_forge_engine.project.quarantine import QuarantinedAsset, list_quarantined, restore_asset
from solar_forge_engine.project.workspace import Project


class QuarantineWorker(QThread):
    def __init__(self, project: Project, asset: QuarantinedAsset | None = None) -> None:
        super().__init__()
        self.project = project
        self.asset = asset
        self.entries: tuple[QuarantinedAsset, ...] = ()
        self.error: str | None = None

    def run(self) -> None:
        try:
            if self.asset is None:
                self.entries = list_quarantined(self.project)
            else:
                restore_asset(self.project, self.asset)
        except (OSError, ValueError) as error:
            self.error = str(error)


class QuarantineDialog(QDialog):
    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.restored = False
        self.entries: tuple[QuarantinedAsset, ...] = ()
        self._job: QuarantineWorker | None = None
        self.setWindowTitle(f"Quarantined assets — {project.name}")
        self.resize(760, 420)
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel("Restore a selected file to assets/. Existing files are never overwritten.")
        )
        self.files = QListWidget()
        self.files.setAccessibleName("Quarantined asset files")
        layout.addWidget(self.files)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.restore_button = QPushButton("Restore selected asset")
        self.restore_button.clicked.connect(self.restore_selected)
        layout.addWidget(self.restore_button)
        self.refresh_button = QPushButton("Refresh quarantine")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.files.currentRowChanged.connect(self._update_actions)
        self.refresh()

    def _update_actions(self) -> None:
        self.restore_button.setEnabled(
            self._job is None and 0 <= self.files.currentRow() < len(self.entries)
        )
        self.refresh_button.setEnabled(self._job is None)

    def _start(self, asset: QuarantinedAsset | None = None) -> None:
        if self._job is not None:
            return
        job = QuarantineWorker(self.project, asset)
        self._job = job
        self.status.setText("Restoring asset…" if asset else "Scanning quarantine…")
        self._update_actions()
        job.finished.connect(lambda: self._finished(job))
        job.start()

    def refresh(self) -> None:
        self._start()

    def restore_selected(self) -> None:
        index = self.files.currentRow()
        if 0 <= index < len(self.entries):
            self._start(self.entries[index])

    def _finished(self, job: QuarantineWorker) -> None:
        self._job = None
        job.deleteLater()
        if job.error:
            self.status.setText(f"Operation stopped: {job.error}")
            if job.asset is None:
                self.entries = ()
                self.files.clear()
        elif job.asset is not None:
            self.restored = True
            self.entries = tuple(asset for asset in self.entries if asset != job.asset)
            self._populate()
            self.status.setText("Asset restored. Scene data was not changed.")
        else:
            self.entries = job.entries
            self._populate()
            self.status.setText(
                f"{len(self.entries)} quarantined files. No files are permanently deleted."
            )
        self._update_actions()

    def _populate(self) -> None:
        self.files.clear()
        for asset in self.entries:
            self.files.addItem(f"{asset.reference} · {asset.size} bytes")

    def reject(self) -> None:
        if self._job is not None:
            self.status.setText("Finishing the current operation; close again shortly.")
            return
        super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._job is not None:
            event.ignore()
        else:
            super().closeEvent(event)
