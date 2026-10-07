"""Asynchronous, bounded JSON communication with the restricted Python worker."""

import json
import os
import sys
from importlib.resources import files
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from solar_forge_engine.runtime.script_worker import (
    MAX_COMMANDS,
    MAX_MESSAGE_BYTES,
    MAX_OUTPUT_BYTES,
)


class ScriptRunner(QObject):
    completed = Signal(str, object)
    failed = Signal(str, int)
    stopped = Signal()
    output = Signal(str)

    def __init__(
        self, source: str, state: dict[str, object], parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self.source = source
        self.initial_state = state
        self.process = QProcess(self)
        environment = QProcessEnvironment()
        environment.insert("LANG", "C.UTF-8")
        environment.insert("LC_ALL", "C.UTF-8")
        environment.insert("LD_LIBRARY_PATH", str(Path(sys.base_prefix) / "lib"))
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory("/")
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._read_error)
        self.process.finished.connect(self._finished)
        self.process.errorOccurred.connect(self._process_error)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(lambda: self._fail("Script exceeded its response deadline."))
        self._buffer = bytearray()
        self._sequence = 0
        self._pending: tuple[int, str] | None = None
        self._booting = True
        self._stopping = False
        self.broken = False

    @property
    def active(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    @property
    def idle(self) -> bool:
        return not self._booting and not self._stopping and self._pending is None and self.active

    def start(self) -> None:
        bootstrap = files("solar_forge_engine.runtime").joinpath("script_worker.py").read_text()
        self.process.start(sys.executable, ["-I", "-S", "-B", "-c", bootstrap, str(os.getpid())])
        self.deadline.start(3000)

    def update(self, state: dict[str, object], dt: float) -> None:
        if self.idle:
            self._request("update", state, dt)

    def _request(self, operation: str, state: dict[str, object], dt: float = 0) -> None:
        self._sequence += 1
        request: dict[str, object] = {
            "id": self._sequence,
            "op": operation,
            "state": state,
            "dt": dt,
        }
        if operation == "start":
            request["source"] = self.source
        try:
            raw = (json.dumps(request, allow_nan=False, ensure_ascii=False) + "\n").encode()
            if len(raw) > MAX_MESSAGE_BYTES:
                raise ValueError("Script context exceeds 128 KiB; use a smaller scene.")
        except (ValueError, UnicodeError) as error:
            self._fail(str(error))
            return
        self._pending = (self._sequence, operation)
        if self.process.write(raw) != len(raw):
            self._fail("Could not send the script request.")
            return
        self.deadline.start(1000 if operation == "start" else 250)

    def _read(self) -> None:
        if self._stopping:
            return
        self._buffer.extend(bytes(self.process.read(MAX_MESSAGE_BYTES + 1).data()))
        if len(self._buffer) > MAX_MESSAGE_BYTES:
            self._fail("Script output exceeded 128 KiB.")
            return
        while b"\n" in self._buffer and not self._stopping:
            raw, _, remainder = self._buffer.partition(b"\n")
            self._buffer = bytearray(remainder)
            try:
                self._receive(json.loads(raw))
            except (ValueError, UnicodeError, RecursionError) as error:
                self._fail(f"Invalid script response: {error}")

    def _receive(self, message: object) -> None:
        if not isinstance(message, dict):
            raise ValueError("Expected a JSON object.")
        if self._booting:
            if message == {"type": "ready"}:
                self._booting = False
                self._request("start", self.initial_state)
            else:
                detail = message.get("message", "Kernel restrictions were not installed.")
                self._fail(f"Script isolation unavailable: {str(detail)[:500]}")
            return
        if (
            self._pending is None
            or type(message.get("id")) is not int
            or message["id"] != self._pending[0]
        ):
            raise ValueError("Unexpected script request ID.")
        if message.get("type") == "error":
            line = message.get("line", 0)
            if type(line) is not int or not 0 <= line <= self.source.count("\n") + 1:
                line = 0
            self._fail(str(message.get("message", "Script failed."))[:600], line)
            return
        if set(message) != {"type", "id", "commands", "output"} or message["type"] != "result":
            raise ValueError("Unknown response fields.")
        commands, output = message["commands"], message["output"]
        if not isinstance(commands, list) or len(commands) > MAX_COMMANDS:
            raise ValueError("Too many script commands.")
        if not isinstance(output, str) or len(output.encode()) > MAX_OUTPUT_BYTES:
            raise ValueError("Script log exceeded 4 KiB.")
        operation = self._pending[1]
        self._pending = None
        self.deadline.stop()
        if output:
            self.output.emit(output)
        self.completed.emit(operation, commands)

    def _read_error(self) -> None:
        self.process.setReadChannel(QProcess.ProcessChannel.StandardError)
        raw = bytes(self.process.read(MAX_OUTPUT_BYTES + 1).data())
        self.process.setReadChannel(QProcess.ProcessChannel.StandardOutput)
        if not self._stopping and raw:
            self._fail("Script worker error: " + raw[:1000].decode("utf-8", errors="replace"))

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if not self._stopping:
            self._fail(f"Script worker stopped: {self.process.errorString()}")

    def _finished(self) -> None:
        self._read()
        if not self._stopping:
            self._fail("Script worker exited unexpectedly.")
        self.deadline.stop()
        self.stopped.emit()

    def _fail(self, message: str, line: int = 0) -> None:
        if self._stopping:
            return
        self.broken = True
        self.stop()
        self.failed.emit(message[:1000], line)

    def stop(self) -> None:
        self._stopping = True
        self._pending = None
        self.deadline.stop()
        if self.active:
            self.process.kill()
