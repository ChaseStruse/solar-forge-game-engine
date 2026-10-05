"""Optional PipeWire preview of validated project PCM, with background library I/O."""

import subprocess
from pathlib import Path
from typing import Literal

from PySide6.QtCore import QProcess, QThread, QTimer
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

from solar_forge_engine.project.audio import Sound, import_wav, list_sounds, load_sound
from solar_forge_engine.project.workspace import Project

PIPEWIRE_PLAYER = "/usr/bin/pw-play"
Operation = Literal["scan", "import", "preview"]


class SoundWorker(QThread):
    def __init__(self, project: Project, operation: Operation, target: str = "") -> None:
        super().__init__()
        self.project = project
        self.operation = operation
        self.target = target
        self.entries: tuple[Sound, ...] = ()
        self.sound: Sound | None = None
        self.pcm = b""
        self.raw_option = False
        self.error: str | None = None

    def run(self) -> None:
        try:
            if self.operation == "preview":
                self.sound, self.pcm = load_sound(self.project, self.target)
                # Older PipeWire uses raw stdin automatically; newer versions need --raw.
                probe = subprocess.run(
                    [PIPEWIRE_PLAYER, "--help"],
                    input=b"",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=2,
                    check=False,
                )
                if probe.returncode != 0:
                    raise ValueError("The PipeWire player could not report its supported options.")
                self.raw_option = b"--raw" in probe.stdout
            else:
                if self.operation == "import":
                    self.sound = import_wav(self.project, Path(self.target))
                self.entries = list_sounds(self.project)
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            self.error = str(error)


class SoundsDialog(QDialog):
    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.project = project
        self.entries: tuple[Sound, ...] = ()
        self._job: SoundWorker | None = None
        self._pcm = b""
        self._closing = False
        self._stopped = False
        self._failed = False
        self._diagnostic = b""
        self.setWindowTitle(f"Sounds — {project.name}")
        self.resize(620, 380)
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Import short WAV clips into this project's audio/ folder. "
            "Preview uses PipeWire at 25% volume. Gameplay sound triggers are coming later."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.files = QListWidget()
        self.files.setAccessibleName("Project sounds")
        layout.addWidget(self.files)
        self.status = QLabel()
        self.status.setWordWrap(True)
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
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        layout.addWidget(close)
        self.process = QProcess(self)
        self.process.started.connect(self._send_pcm)
        self.process.finished.connect(self._play_finished)
        self.process.errorOccurred.connect(self._play_error)
        self.process.readyReadStandardError.connect(self._read_error)
        self.process.readyReadStandardOutput.connect(self._drain_output)
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self.process.kill)
        self.import_button.clicked.connect(self.choose_import)
        self.preview_button.clicked.connect(self.preview)
        self.stop_button.clicked.connect(self.stop)
        self.refresh_button.clicked.connect(lambda: self._start("scan"))
        self.files.currentRowChanged.connect(self._selection_changed)
        self._start("scan")

    def _playing(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def _update_actions(self) -> None:
        idle = self._job is None and not self._playing()
        self.import_button.setEnabled(idle)
        self.refresh_button.setEnabled(idle)
        self.preview_button.setEnabled(idle and 0 <= self.files.currentRow() < len(self.entries))
        self.stop_button.setEnabled(self._playing())
        self.files.setEnabled(self._job is None)

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
        elif job.operation == "preview":
            assert job.sound is not None
            self._pcm = job.pcm
            self._diagnostic = b""
            self._stopped = self._failed = False
            self.process.setProgram(PIPEWIRE_PLAYER)
            self.process.setArguments(
                (["--raw"] if job.raw_option else [])
                + [
                    "--rate",
                    str(job.sound.rate),
                    "--channels",
                    str(job.sound.channels),
                    "--format",
                    "u8" if job.sound.width == 1 else "s16",
                    "--volume",
                    "0.25",
                    "-",
                ]
            )
            self.status.setText(f"Previewing {job.sound.name}…")
            self.process.start()
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

    def _send_pcm(self) -> None:
        self.process.write(self._pcm)
        self._pcm = b""
        self.process.closeWriteChannel()

    def _read_error(self) -> None:
        raw = self.process.readAllStandardError().data()
        self._diagnostic = (self._diagnostic + raw)[-2048:]

    def _drain_output(self) -> None:
        self.process.readAllStandardOutput()

    def _play_error(self, error: QProcess.ProcessError) -> None:
        self._failed = True
        self._pcm = b""
        self.status.setText(
            "Preview unavailable. Install pipewire-audio on Arch and ensure PipeWire is running. "
            f"{self.process.errorString()}"
        )
        if error == QProcess.ProcessError.FailedToStart:
            self._update_actions()
            if self._closing:
                super().reject()

    def _play_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._kill_timer.stop()
        self._pcm = b""
        self._read_error()
        if self._stopped:
            self.status.setText("Preview stopped.")
        elif not self._failed:
            if code == 0 and status == QProcess.ExitStatus.NormalExit:
                self.status.setText("Preview finished.")
            else:
                detail = self._diagnostic.decode("utf-8", errors="replace").strip()
                self.status.setText(
                    f"PipeWire preview failed: {detail or 'audio output unavailable'}"
                )
        self._update_actions()
        if self._closing:
            super().reject()

    def stop(self) -> None:
        if self._playing():
            self._stopped = True
            self.process.terminate()
            self._kill_timer.start(250)

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
