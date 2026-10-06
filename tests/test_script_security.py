import os
import subprocess
import sys
from importlib.resources import files


def test_real_worker_restrictions_deny_ambient_access_and_process_escape(tmp_path):
    canary = tmp_path / "credentials.txt"
    canary.write_text("synthetic credential")
    marker = tmp_path / "executed"
    source = files("solar_forge_engine.runtime").joinpath("script_security.py").read_text()
    checks = """
import json, math, socket, subprocess, sys, resource
from pathlib import Path
canary, marker, inherited, parent = sys.argv[1:]
abi = enforce()
def denied(operation):
    try:
        operation()
    except (OSError, ImportError):
        return True
    return False
report = {
    'read': denied(lambda: Path(canary).read_text()),
    'write': denied(lambda: Path(canary).write_text('changed')),
    'socket': denied(lambda: socket.socket()),
    'exec': denied(lambda: subprocess.run(['/usr/bin/touch', marker], check=True)),
    'fork': denied(os.fork),
    'signal': denied(lambda: os.kill(int(parent), 0)),
    'descriptor': denied(lambda: os.read(int(inherited), 64)),
    'editor_import': denied(lambda: __import__('solar_forge_engine.editor.window')),
    'math': math.sqrt(81) == 9,
}
try:
    bytearray(300 * 1024 * 1024)
except MemoryError:
    report['memory_limit'] = True
else:
    report['memory_limit'] = False
print(json.dumps({'abi': abi, 'checks': report}))
if not all(report.values()):
    raise SystemExit(1)
"""
    with canary.open("rb") as handle:
        result = subprocess.run(
            [
                sys.executable,
                "-I",
                "-S",
                "-c",
                source + checks,
                str(canary),
                str(marker),
                str(handle.fileno()),
                str(os.getpid()),
            ],
            pass_fds=(handle.fileno(),),
            env={},
            cwd="/",
            capture_output=True,
            text=True,
            timeout=5,
        )
    assert result.returncode == 0, result.stdout + result.stderr
    assert canary.read_text() == "synthetic credential"
    assert not marker.exists()


def test_busy_behavior_dies_when_its_runtime_parent_exits():
    import signal
    import time
    from pathlib import Path

    code = """import os
from PySide6.QtCore import QCoreApplication, QTimer
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.script import ScriptBinding
from solar_forge_engine.runtime.script_host import ScriptHost
app = QCoreApplication([])
source = "def update(ctx, dt):\\n    while True: pass\\n"
binding = ScriptBinding.from_source('actor', 'busy', source)
host = ScriptHost(Scene(entities=(Entity('actor'),), scripts=(binding,)))
host.result.connect(lambda result: host.step(0.01, 0.01, [], {'actor': (0, 0)}, []))
def check():
    if host._id == 1 and host._progress:
        print(host.process.processId(), flush=True)
        os._exit(0)
    if host.failed:
        os._exit(2)
timer = QTimer()
timer.timeout.connect(check)
timer.start(1)
QTimer.singleShot(5000, lambda: os._exit(3))
host.start()
app.exec()
"""
    parent = subprocess.run(
        [sys.executable, "-I", "-c", code],
        env={},
        cwd="/",
        capture_output=True,
        text=True,
        timeout=7,
    )
    assert parent.returncode == 0, parent.stderr
    identity = int(parent.stdout.strip())
    state = Path(f"/proc/{identity}/stat")
    try:
        deadline = time.monotonic() + 2
        while state.exists():
            try:
                status = state.read_text().split(")", 1)[1].split()[0]
            except FileNotFoundError:
                break
            if status == "Z":  # Already killed; the system reaper may not have collected it yet.
                break
            assert time.monotonic() < deadline, "Busy behavior survived its runtime parent."
            time.sleep(0.01)
    finally:
        try:
            os.kill(identity, signal.SIGKILL)
        except ProcessLookupError:
            pass
