"""Asynchronous, deadline-bound OS-restricted Python behavior process."""

import json
import sys
from dataclasses import asdict
from importlib.resources import files

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.runtime.script_protocol import (
    MAX_INPUT_BYTES,
    MAX_PACKET_BYTES,
    ScriptFault,
    parse_result,
)


def bootstrap() -> str:
    """Only trusted runtime helpers enter the child; project source travels over stdin."""
    lines = [
        "import sys, types",
        "for name in ('solar_forge_engine', 'solar_forge_engine.runtime'):",
        "    package = types.ModuleType(name); package.__path__ = []; sys.modules[name] = package",
    ]
    resources = files("solar_forge_engine.runtime")
    for name in ("script_protocol", "script_security", "script_worker"):
        source = resources.joinpath(f"{name}.py").read_text(encoding="utf-8")
        if len(source.encode()) > 256 * 1024:
            raise ValueError("Trusted behavior helper exceeds its size limit.")
        qualified = f"solar_forge_engine.runtime.{name}"
        lines.extend(
            (
                f"module = types.ModuleType({qualified!r})",
                "module.__package__ = 'solar_forge_engine.runtime'",
                f"module.__file__ = {name + '.py'!r}",
                f"sys.modules[{qualified!r}] = module",
                f"exec(compile({source!r}, module.__file__, 'exec'), module.__dict__)",
            )
        )
    lines.append("raise SystemExit(module.worker_main())")
    code = "\n".join(lines)
    if len(code.encode()) > 96 * 1024:
        raise ValueError("Trusted behavior bootstrap exceeds the Linux argument limit.")
    return code


class ScriptHost(QObject):
    result = Signal(object)
    fault = Signal(object)
    finished = Signal()

    def __init__(self, scene: Scene, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.scene = scene
        self.bindings = {binding.entity_id: binding.path for binding in scene.scripts}
        self.process = QProcess(self)
        self.process.setProcessEnvironment(QProcessEnvironment())
        self.process.setWorkingDirectory("/")
        self.process.setProgram(sys.executable)
        self.process.setArguments(["-I", "-S", "-c", bootstrap()])
        self.process.readyReadStandardOutput.connect(self._read)
        self.process.readyReadStandardError.connect(self._read_error)
        self.process.finished.connect(self._exited)
        self.process.errorOccurred.connect(self._process_error)
        self.deadline = QTimer(self)
        self.deadline.setSingleShot(True)
        self.deadline.timeout.connect(lambda: self._fail("Python callback exceeded its deadline."))
        self.ready = False
        self.busy = False
        self.stopping = False
        self.failed = False
        self._id = -1
        self._running = next(iter(self.bindings), "")
        self._buffer = bytearray()
        self._stderr = bytearray()
        self._received = 0
        self._progress = 0

    @property
    def active(self) -> bool:
        return self.process.state() != QProcess.ProcessState.NotRunning

    def start(self) -> None:
        if not self.bindings:
            return
        self.process.start()
        self._send(
            {
                "op": "init",
                "scripts": [asdict(binding) for binding in self.scene.scripts],
                "entities": [
                    {
                        "id": entity.id,
                        "name": entity.name,
                        "x": entity.x,
                        "y": entity.y,
                        "width": entity.width,
                        "height": entity.height,
                        "color": entity.color,
                        "role": entity.role.value,
                    }
                    for entity in self.scene.entities
                ],
            },
            5000,
        )

    def step(
        self,
        dt: float,
        elapsed: float,
        keys: list[str],
        positions: dict[str, tuple[float, float]],
        events: list[dict[str, str]],
    ) -> bool:
        if not self.ready or self.busy or self.stopping or self.failed:
            return False
        self._send(
            {
                "op": "step",
                "dt": dt,
                "elapsed": elapsed,
                "input": keys,
                "positions": positions,
                "events": events,
            },
            250,
        )
        return True

    def stop(self) -> None:
        if self.stopping:
            return
        self.stopping = True
        if not self.active:
            return
        if self.ready and not self.busy and not self.failed:
            self._send({"op": "stop"}, 250)
        else:
            self.process.kill()

    def _send(self, value: dict[str, object], timeout: int) -> None:
        self._id += 1
        raw = json.dumps(dict(value, id=self._id), allow_nan=False).encode() + b"\n"
        if len(raw) > MAX_INPUT_BYTES:
            self._fail("Python input snapshot exceeds its size limit.")
            return
        self.busy = True
        self._received = self._progress = 0
        self.deadline.start(timeout)
        self.process.write(raw)

    def _read(self) -> None:
        raw = bytes(self.process.readAllStandardOutput().data())
        self._received += len(raw)
        self._buffer.extend(raw)
        if self._received > 256 * 1024:
            self._fail("Python output exceeded its size limit.")
            return
        while b"\n" in self._buffer and not self.failed:
            line, _, rest = self._buffer.partition(b"\n")
            self._buffer = bytearray(rest)
            if len(line) > MAX_PACKET_BYTES or not self.busy:
                self._fail("Unexpected or oversized Python response.")
                return
            try:
                packet = json.loads(line)
                if isinstance(packet, dict) and set(packet) == {"id", "running"}:
                    actor = packet["running"]
                    if (
                        type(packet["id"]) is not int
                        or packet["id"] != self._id
                        or not isinstance(actor, str)
                        or actor not in self.bindings
                        or self._progress >= 64
                    ):
                        raise ValueError("Invalid Python callback progress.")
                    self._progress += 1
                    self._running = actor
                    continue
                response = parse_result(packet, self._id, self.bindings)
            except (ValueError, TypeError, RecursionError) as error:
                self._fail(str(error))
                return
            self.deadline.stop()
            self.busy = False
            self.ready = True
            if response.fault is not None:
                self.failed = True
                self.fault.emit(response.fault)
                self.process.kill()
            self.result.emit(response)
        if len(self._buffer) > MAX_PACKET_BYTES:
            self._fail("Python response exceeded its size limit.")

    def _read_error(self) -> None:
        self._stderr.extend(bytes(self.process.readAllStandardError().data()))
        if len(self._stderr) > 8192:
            self._fail("Python diagnostic output exceeded its size limit.")

    def _fail(self, message: str) -> None:
        if self.failed:
            return
        self.failed = True
        self.ready = False
        self.busy = False
        self.deadline.stop()
        self.fault.emit(
            ScriptFault(self._running, self.bindings.get(self._running, ""), 0, message[:2048])
        )
        if self.active:
            self.process.kill()

    def _process_error(self, error: QProcess.ProcessError) -> None:
        if not self.stopping and error == QProcess.ProcessError.FailedToStart:
            self._fail(self.process.errorString())
            self.finished.emit()

    def _exited(self, code: int, status: QProcess.ExitStatus) -> None:
        self._read()
        self._read_error()
        self.deadline.stop()
        if not self.failed and not self.stopping:
            detail = self._stderr.decode("utf-8", errors="replace").strip()
            self._fail(detail or f"Python worker exited unexpectedly ({code}).")
        self.ready = self.busy = False
        self.finished.emit()
