"""One optional PipeWire voice, with asynchronous discovery and bounded shutdown."""

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

PIPEWIRE_PLAYER = "/usr/bin/pw-play"


class SoundPlayer(QObject):
    message = Signal(str)
    changed = Signal()
    finished = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.process = QProcess(self)
        self.probe = QProcess(self)
        self._raw_option: bool | None = None
        self._help = b""
        self._diagnostic = b""
        self._pcm = b""
        self._rate = 8000
        self._channels = 1
        self._width = 2
        self._stopped = False
        self._failed = False
        self._pending = False
        self._probe_timer = QTimer(self)
        self._probe_timer.setSingleShot(True)
        self._probe_timer.timeout.connect(self._probe_timeout)
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.timeout.connect(self._kill)
        self.probe.started.connect(self.probe.closeWriteChannel)
        self.probe.readyReadStandardOutput.connect(self._read_help)
        self.probe.readyReadStandardError.connect(self._read_help_error)
        self.probe.finished.connect(self._probe_finished)
        self.probe.errorOccurred.connect(self._probe_error)
        self.process.started.connect(self._send_pcm)
        self.process.readyReadStandardError.connect(self._read_error)
        self.process.readyReadStandardOutput.connect(self.process.readAllStandardOutput)
        self.process.finished.connect(self._play_finished)
        self.process.errorOccurred.connect(self._play_error)

    @property
    def active(self) -> bool:
        return self._pending or any(
            process.state() != QProcess.ProcessState.NotRunning
            for process in (self.process, self.probe)
        )

    def play(self, pcm: bytes, rate: int, channels: int, width: int) -> bool:
        """Play already validated PCM. Overlapping requests share the current voice."""
        if self.active:
            return False
        self._pcm, self._rate, self._channels, self._width = pcm, rate, channels, width
        self._diagnostic = self._help = b""
        self._stopped = self._failed = False
        self._pending = True
        if self._raw_option is None:
            self.probe.setProgram(PIPEWIRE_PLAYER)
            self.probe.setArguments(["--help"])
            self.probe.start()
            self._probe_timer.start(2000)
        else:
            self._start_play()
        self.changed.emit()
        return True

    def _read_help(self) -> None:
        self._help = (self._help + self.probe.readAllStandardOutput().data())[-16_384:]

    def _read_help_error(self) -> None:
        self._help = (self._help + self.probe.readAllStandardError().data())[-16_384:]

    def _probe_timeout(self) -> None:
        self._failed = True
        self.message.emit("Preview unavailable: PipeWire option discovery timed out.")
        self.probe.kill()

    def _probe_error(self, error: QProcess.ProcessError) -> None:
        if not self._stopped:
            self._failed = True
            self.message.emit(
                "Preview unavailable. Install pipewire-audio and ensure PipeWire is running. "
                f"{self.probe.errorString()}"
            )
        if error == QProcess.ProcessError.FailedToStart:
            self._probe_timer.stop()
            self._pending = False
            self._complete()

    def _probe_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._probe_timer.stop()
        self._read_help()
        self._read_help_error()
        if not self._stopped and not self._failed and code == 0:
            # Debian's older client assumes raw stdin; Arch's newer client needs --raw.
            self._raw_option = b"--raw" in self._help
            self._start_play()
        else:
            if not self._failed and not self._stopped:
                self.message.emit("Preview unavailable: PipeWire option discovery failed.")
            self._pending = False
            self._complete()

    def _start_play(self) -> None:
        self.process.setProgram(PIPEWIRE_PLAYER)
        self.process.setArguments(
            (["--raw"] if self._raw_option else [])
            + [
                "--rate",
                str(self._rate),
                "--channels",
                str(self._channels),
                "--format",
                "u8" if self._width == 1 else "s16",
                "--volume",
                "0.25",
                "-",
            ]
        )
        self.process.start()
        self._pending = False

    def _send_pcm(self) -> None:
        self.process.write(self._pcm)
        self._pcm = b""
        self.process.closeWriteChannel()

    def _read_error(self) -> None:
        self._diagnostic = (self._diagnostic + self.process.readAllStandardError().data())[-2048:]

    def _play_error(self, error: QProcess.ProcessError) -> None:
        self._failed = True
        if not self._stopped:
            self.message.emit(f"Preview unavailable: {self.process.errorString()}")
        if error == QProcess.ProcessError.FailedToStart:
            self._complete()

    def _play_finished(self, code: int, status: QProcess.ExitStatus) -> None:
        self._read_error()
        if self._stopped:
            self.message.emit("Preview stopped.")
        elif not self._failed:
            if code == 0 and status == QProcess.ExitStatus.NormalExit:
                self.message.emit("Preview finished.")
            else:
                detail = self._diagnostic.decode("utf-8", errors="replace").strip()
                self.message.emit(
                    f"PipeWire preview failed: {detail or 'audio output unavailable'}"
                )
        self._complete()

    def _complete(self) -> None:
        self._pcm = b""
        if not self.active:
            self._kill_timer.stop()
            self.changed.emit()
            self.finished.emit()

    def stop(self) -> None:
        self._stopped = True
        self._pending = False
        if self.active:
            for process in (self.process, self.probe):
                if process.state() != QProcess.ProcessState.NotRunning:
                    process.terminate()
            self._kill_timer.start(250)
        else:
            self._complete()

    def _kill(self) -> None:
        for process in (self.process, self.probe):
            if process.state() != QProcess.ProcessState.NotRunning:
                process.kill()
