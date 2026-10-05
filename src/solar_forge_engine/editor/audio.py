"""Optional PipeWire preview of validated project PCM, with background library I/O."""

from pathlib import Path
from typing import Literal

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from solar_forge_engine.core.audio import SoundClip
from solar_forge_engine.project.audio import Sound, import_wav, list_sounds, load_clip, load_sound
from solar_forge_engine.project.workspace import Project
from solar_forge_engine.runtime.audio import SoundPlayer

Operation = Literal["scan", "import", "preview", "choose"]


class SoundWorker(QThread):
    def __init__(self, project: Project, operation: Operation, target: str = "") -> None:
        super().__init__()
        self.project = project
        self.operation = operation
        self.target = target
        self.entries: tuple[Sound, ...] = ()
        self.sound: Sound | None = None
        self.pcm = b""
        self.clip: SoundClip | None = None
        self.error: str | None = None

    def run(self) -> None:
        try:
            if self.operation == "choose":
                self.clip = load_clip(self.project.root, self.target)
            elif self.operation == "preview":
                self.sound, self.pcm = load_sound(self.project, self.target)
            else:
                if self.operation == "import":
                    self.sound = import_wav(self.project, Path(self.target))
                self.entries = list_sounds(self.project)
        except (OSError, ValueError) as error:
            self.error = str(error)


class SoundsDialog(QDialog):
    def __init__(
        self,
        project: Project,
        parent: QWidget | None = None,
        *,
        coin_sound: SoundClip | None = None,
    ) -> None:
        super().__init__(parent)
        self.project = project
        self.coin_sound = coin_sound
        self.sound_changed = False
        self.chosen_clip: SoundClip | None = None
        self.entries: tuple[Sound, ...] = ()
        self._job: SoundWorker | None = None
        self._closing = False
        self.setWindowTitle(f"Sounds — {project.name}")
        self.resize(620, 380)
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Import short WAV clips into this project's audio/ folder. "
            "Preview uses PipeWire at 25% volume. Use a clip when coins are collected in Play."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.files = QListWidget()
        self.files.setAccessibleName("Project sounds")
        layout.addWidget(self.files)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.import_button = QPushButton("Import WAV…")
        self.preview_button = QPushButton("Preview")
        self.stop_button = QPushButton("Stop")
        self.refresh_button = QPushButton("Refresh")
        for button in (
            self.import_button,
            self.preview_button,
            self.stop_button,
            self.refresh_button,
        ):
            row.addWidget(button)
        layout.addLayout(row)
        self.assigned = QLabel(
            f"Coin collection sound: {coin_sound.duration:.2f} s"
            if coin_sound
            else "Coin collection sound: None"
        )
        layout.addWidget(self.assigned)
        assign_row = QHBoxLayout()
        self.use_button = QPushButton("Use for coin collection")
        self.clear_button = QPushButton("Remove collection sound")
        assign_row.addWidget(self.use_button)
        assign_row.addWidget(self.clear_button)
        layout.addLayout(assign_row)
        self.use_button.clicked.connect(self.choose_sound)
        self.clear_button.clicked.connect(self.clear_sound)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.playback = SoundPlayer(self)
        self.process = self.playback.process
        self.playback.message.connect(self.status.setText)
        self.playback.changed.connect(self._update_actions)
        self.playback.finished.connect(self._play_finished)
        self.import_button.clicked.connect(self.choose_import)
        self.preview_button.clicked.connect(self.preview)
        self.stop_button.clicked.connect(self.stop)
        self.refresh_button.clicked.connect(lambda: self._start("scan"))
        self.files.currentRowChanged.connect(self._selection_changed)
        self._start("scan")

    def _playing(self) -> bool:
        return self.playback.active

    def _update_actions(self) -> None:
        idle = self._job is None and not self._playing()
        self.import_button.setEnabled(idle)
        self.refresh_button.setEnabled(idle)
        self.preview_button.setEnabled(idle and 0 <= self.files.currentRow() < len(self.entries))
        self.stop_button.setEnabled(self._playing())
        self.files.setEnabled(self._job is None)
        self.use_button.setEnabled(idle and 0 <= self.files.currentRow() < len(self.entries))
        self.clear_button.setEnabled(idle and self.coin_sound is not None)

    def _start(self, operation: Operation, target: str = "") -> None:
        if self._job is not None or self._playing():
            return
        job = SoundWorker(self.project, operation, target)
        self._job = job
        self.status.setText("Loading sounds…" if operation == "scan" else "Preparing sound…")
        self._update_actions()
        job.finished.connect(lambda: self._finished(job))
        job.start()

    def choose_import(self) -> None:
        if self._job is not None or self._playing():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Import sound", "", "PCM WAV (*.wav)")
        if filename:
            self._start("import", filename)

    def preview(self) -> None:
        index = self.files.currentRow()
        if 0 <= index < len(self.entries):
            self._start("preview", self.entries[index].reference)

    def choose_sound(self) -> None:
        index = self.files.currentRow()
        if 0 <= index < len(self.entries):
            self._start("choose", self.entries[index].reference)

    def clear_sound(self) -> None:
        if self._job is None and not self._playing() and self.coin_sound is not None:
            self.sound_changed = True
            self.chosen_clip = None
            super().accept()

    def _finished(self, job: SoundWorker) -> None:
        self._job = None
        job.deleteLater()
        if job.error:
            self.status.setText(
                "Preview unavailable. Install pipewire-audio and ensure PipeWire is running. "
                f"{job.error}"
                if job.operation == "preview"
                else f"Sound operation stopped: {job.error}"
            )
            if job.operation == "scan":
                self.entries = ()
                self.files.clear()
        elif job.operation == "choose":
            self.sound_changed = True
            self.chosen_clip = job.clip
            super().accept()
        elif job.operation == "preview":
            assert job.sound is not None
            self.status.setText(f"Previewing {job.sound.name}…")
            self.playback.play(job.pcm, job.sound.rate, job.sound.channels, job.sound.width)
        else:
            self.entries = job.entries
            self.files.clear()
            for sound in self.entries:
                self.files.addItem(
                    f"{sound.name} · {sound.duration:.2f} s · {sound.rate} Hz · "
                    f"{'mono' if sound.channels == 1 else 'stereo'} · {sound.width * 8} bit"
                )
            if job.sound in self.entries:
                self.files.setCurrentRow(self.entries.index(job.sound))
            self.status.setText(f"{len(self.entries)} project sounds. Select a clip to preview.")
        self._update_actions()

    def _play_finished(self) -> None:
        self._update_actions()
        if self._closing:
            super().reject()

    def stop(self) -> None:
        if self._playing():
            self.playback.stop()

    def _selection_changed(self) -> None:
        self.stop()
        self._update_actions()

    def reject(self) -> None:
        if self._job is not None:
            self.status.setText("Finishing sound I/O; close again shortly.")
        elif self._playing():
            self._closing = True
            self.stop()
        else:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._job is not None or self._playing():
            event.ignore()
            self.reject()
        else:
            super().closeEvent(event)
