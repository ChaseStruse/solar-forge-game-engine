import pytest

from solar_forge_engine.core.scene import Entity, Role, Scene
from solar_forge_engine.runtime.player import PlayerWindow
from solar_forge_engine.runtime.scripting import ScriptRunner
from solar_forge_engine.runtime.simulation import Simulation


def scene(source=""):
    return Scene(
        "Script fixture",
        (Entity("player", role=Role.PLAYER), Entity("coin", x=100, role=Role.COIN)),
        script=source,
    )


def test_runtime_commands_are_atomic_and_never_change_authored_data():
    authored = scene()
    simulation = Simulation(authored, "player")
    with pytest.raises(ValueError):
        simulation.apply_script(
            [
                {"op": "position", "id": "coin", "x": 200, "y": 0},
                {"op": "speed", "value": float("nan")},
            ]
        )
    assert simulation.runtime_scene == authored
    simulation.apply_script(
        [
            {"op": "position", "id": "coin", "x": 200, "y": 0},
            {"op": "speed", "value": 400},
            {"op": "message", "value": "<b>Literal text</b>"},
        ]
    )
    assert simulation.coins[0].x == 200 and simulation.speed == 400
    assert simulation.scene == authored and authored.entity("coin").x == 100
    assert simulation.message == "<b>Literal text</b>"


@pytest.mark.parametrize(
    "source, expected",
    [
        ("while True: pass", "deadline"),
        ("import os\nwhile True: os.write(1, b'x' * 65536)", "128 KiB"),
        ("import os\nos._exit(7)", "exited"),
        ("def on_start(game):\n    open('/etc/passwd').read()", "PermissionError"),
    ],
)
def test_bad_script_is_stopped_without_blocking_qt(qtbot, source, expected):
    runner = ScriptRunner(source, Simulation(scene(), "player").script_state(0, 0, 0))
    errors = []
    runner.failed.connect(lambda message, line: errors.append(message))
    runner.start()
    qtbot.waitUntil(lambda: bool(errors), timeout=5000)
    qtbot.waitUntil(lambda: not runner.active, timeout=2000)
    assert expected in errors[0]
    assert len(errors) == 1


def test_script_environment_is_scrubbed_and_stop_terminates_worker(qtbot, monkeypatch):
    monkeypatch.setenv("SCRIPT_CANARY", "synthetic secret")
    source = (
        "import os\ndef on_start(game):\n"
        "    assert 'SCRIPT_CANARY' not in os.environ\n    game.say('isolated')"
    )
    runner = ScriptRunner(source, Simulation(scene(), "player").script_state(0, 0, 0))
    results = []
    runner.completed.connect(lambda operation, commands: results.append(commands))
    runner.start()
    qtbot.waitUntil(lambda: bool(results), timeout=5000)
    assert results[0] == [{"op": "message", "value": "isolated"}]
    runner.stop()
    qtbot.waitUntil(lambda: not runner.active, timeout=2000)


def test_play_scripts_move_objects_pause_restart_and_close(qtbot):
    source = """
def on_start(game):
    game.data["x"] = 100
    game.set_speed(400)
    game.say("Find the moving coin")
def on_update(game, dt):
    game.data["x"] += 120 * dt
    game.set_position("coin", game.data["x"], 0)
"""
    authored = scene(source)
    player = PlayerWindow(authored, "player")
    qtbot.addWidget(player)
    player.show()
    qtbot.waitUntil(lambda: player.simulation.coins[0].x > 100, timeout=5000)
    assert player.simulation.speed == 400
    assert player.items["coin"].pos().x() == player.simulation.coins[0].x
    assert player.script_label.text() == "Find the moving coin"
    player.toggle_pause()
    before = player.simulation.coins[0].x
    qtbot.wait(100)
    assert player.simulation.coins[0].x == before
    first = player._script
    player.restart()
    qtbot.waitUntil(
        lambda: player._script_ready and player.simulation.coins[0].x > 100, timeout=5000
    )
    assert first is not player._script
    assert player.simulation.scene == authored
    runner = player._script
    player.close()
    qtbot.waitUntil(lambda: not runner.active, timeout=2000)


def test_script_error_reports_line_and_restart_does_not_silently_skip_script(qtbot):
    authored = scene("def on_update(game, dt):\n    raise ValueError('fix this')\n")
    player = PlayerWindow(authored, "player")
    qtbot.addWidget(player)
    player.show()
    qtbot.waitUntil(lambda: player._script_failed, timeout=5000)
    assert "line 2" in player.script_label.text()
    assert player.paused
    player.toggle_pause()
    assert player.paused
    assert player.simulation.scene == authored
    player.close()
    qtbot.waitUntil(lambda: not player._script.active, timeout=2000)


def test_missing_isolation_fails_before_any_source_is_sent(qtbot, monkeypatch, tmp_path):
    from pathlib import Path

    from solar_forge_engine.runtime import script_worker, scripting

    bootstrap = (
        Path(script_worker.__file__)
        .read_text()
        .replace("libseccomp.so.2", "missing-forge-seccomp.so")
    )
    (tmp_path / "script_worker.py").write_text(bootstrap)
    monkeypatch.setattr(scripting, "files", lambda package: tmp_path)
    runner = ScriptRunner(
        "raise AssertionError('must not execute')",
        Simulation(scene(), "player").script_state(0, 0, 0),
    )
    failures = []
    runner.failed.connect(lambda message, line: failures.append(message))
    runner.start()
    qtbot.waitUntil(lambda: bool(failures), timeout=5000)
    qtbot.waitUntil(lambda: not runner.active, timeout=2000)
    assert "isolation unavailable" in failures[0]
    assert runner._sequence == 0


def test_parent_death_kills_busy_worker(qtbot):
    import json
    import os
    import select
    import signal
    import subprocess
    import sys
    from pathlib import Path

    from solar_forge_engine.runtime import script_worker

    bootstrap = Path(script_worker.__file__).read_text()
    source = "import os\nos.write(1, b'busy\\n')\nwhile True: pass"
    state = Simulation(scene(), "player").script_state(0, 0, 0)
    request = json.dumps({"id": 1, "op": "start", "source": source, "state": state}) + "\n"
    parent_source = f"""
import os, subprocess, sys, time
child = subprocess.Popen(
    [sys.executable, "-I", "-S", "-B", "-c", {bootstrap!r}, str(os.getpid())],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    env={{"LANG": "C.UTF-8"}}, text=True,
)
assert child.stdout.readline().strip() == '{{"type": "ready"}}'
child.stdin.write({request!r})
child.stdin.flush()
assert child.stdout.readline().strip() == "busy"
print(child.pid, flush=True)
time.sleep(60)
"""
    parent = subprocess.Popen(
        [sys.executable, "-I", "-S", "-c", parent_source], stdout=subprocess.PIPE, text=True
    )
    pidfd = None
    try:
        qtbot.waitUntil(lambda: bool(select.select([parent.stdout], [], [], 0)[0]), timeout=5000)
        child_pid = int(parent.stdout.readline())
        pidfd = os.pidfd_open(child_pid)
        parent.kill()
        parent.wait(timeout=3)
        qtbot.waitUntil(lambda: bool(select.select([pidfd], [], [], 0)[0]), timeout=3000)
    finally:
        if parent.poll() is None:
            parent.kill()
            parent.wait(timeout=3)
        if pidfd is not None:
            try:
                signal.pidfd_send_signal(pidfd, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.close(pidfd)
