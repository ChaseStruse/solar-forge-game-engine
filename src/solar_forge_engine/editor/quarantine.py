"""Native quarantine browser with worker-based scanning, restoration and purge."""

from typing import Literal

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from solar_forge_engine.project.quarantine import (
    QuarantinedAsset,
    list_quarantined,
    purge_asset,
    restore_asset,
)
from solar_forge_engine.project.workspace import Project

Operation = Literal["scan", "restore", "review", "purge"]


class QuarantineWorker(QThread):
    def __init__(
        self, project: Project, asset: QuarantinedAsset | None = None, operation: Operation = "scan"
    ) -> None:
        super().__init__()
        self.project = project
        self.asset = asset
        self.operation = operation
        self.entries: tuple[QuarantinedAsset, ...] = ()
        self.error: str | None = None

    def run(self) -> None:
        try:
            if self.operation == "scan":
                self.entries = list_quarantined(self.project)
            else:
                assert self.asset is not None
                if self.operation == "review":
                    if self.asset not in list_quarantined(self.project):
                        raise ValueError("Quarantined asset changed. Refresh before purging.")
                elif self.operation == "restore":
                    restore_asset(self.project, self.asset)
                else:
                    purge_asset(self.project, self.asset)
        except (OSError, ValueError) as error:
            self.error = str(error)


class QuarantineDialog(QDialog):
    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.restored = False
        self.purged = False
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
        self.purge_button = QPushButton("Review permanent deletion…")
        self.purge_button.setToolTip("Delete only the selected quarantine file after confirmation.")
        self.purge_button.clicked.connect(self.review_purge)
        layout.addWidget(self.purge_button)
        self.refresh_button = QPushButton("Refresh quarantine")
        self.refresh_button.clicked.connect(self.refresh)
        layout.addWidget(self.refresh_button)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.files.currentRowChanged.connect(self._update_actions)
        self.refresh()

    def _update_actions(self) -> None:
        selected = self._job is None and 0 <= self.files.currentRow() < len(self.entries)
        self.restore_button.setEnabled(selected)
        self.purge_button.setEnabled(selected)
        self.refresh_button.setEnabled(self._job is None)

    def _start(self, asset: QuarantinedAsset | None = None, operation: Operation = "scan") -> None:
        if self._job is not None:
            return
        job = QuarantineWorker(self.project, asset, operation)
        self._job = job
        self.status.setText(
            {
                "scan": "Scanning quarantine…",
                "restore": "Restoring asset…",
                "review": "Checking quarantine before deletion…",
                "purge": "Deleting selected file…",
            }[operation]
        )
        self._update_actions()
        job.finished.connect(lambda: self._finished(job))
        job.start()

    def refresh(self) -> None:
        self._start()

    def restore_selected(self) -> None:
        index = self.files.currentRow()
        if 0 <= index < len(self.entries):
            self._start(self.entries[index], "restore")

    def review_purge(self) -> None:
        index = self.files.currentRow()
        if 0 <= index < len(self.entries):
            self._start(self.entries[index], "review")

    def _confirm_purge(self, asset: QuarantinedAsset) -> bool:
        review = QMessageBox(self)
        review.setWindowTitle("Permanently delete quarantined asset?")
        review.setIcon(QMessageBox.Icon.Warning)
        review.setTextFormat(Qt.TextFormat.PlainText)
        review.setText(f"Delete one quarantined file ({asset.size} bytes)?")
        review.setInformativeText(
            f"{asset.reference}\n\nThis cannot be undone. Scene data and assets/ are unchanged."
        )
        review.setDetailedText(f"SHA-256: {asset.fingerprint}")
        review.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        review.setDefaultButton(QMessageBox.StandardButton.No)
        return review.exec() == QMessageBox.StandardButton.Yes

    def _finished(self, job: QuarantineWorker) -> None:
        self._job = None
        job.deleteLater()
        if job.error:
            self.status.setText(f"Operation stopped: {job.error}")
            if job.asset is None:
                self.entries = ()
                self.files.clear()
        elif job.operation == "review":
            assert job.asset is not None
            if self._confirm_purge(job.asset):
                self._start(job.asset, "purge")
                return
            self.status.setText("Deletion cancelled. No files were changed.")
        elif job.asset is not None:
            if job.operation == "restore":
                self.restored = True
            else:
                self.purged = True
            self.entries = tuple(asset for asset in self.entries if asset != job.asset)
            self._populate()
            self.status.setText(
                "Asset restored. Scene data was not changed."
                if job.operation == "restore"
                else "Selected quarantine file permanently deleted. Scene data was not changed."
            )
        else:
            self.entries = job.entries
            self._populate()
            self.status.setText(
                f"{len(self.entries)} quarantined files. "
                "Select a file to restore or review deletion."
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
