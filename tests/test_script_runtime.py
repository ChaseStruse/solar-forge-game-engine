from dataclasses import replace

import pytest

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.script import ScriptBinding
from solar_forge_engine.runtime.script_host import ScriptHost


def scripted(source):
    binding = ScriptBinding.from_source("player", "motion", source)
    return Scene(entities=(Entity("player", x=100, y=100),), scripts=(binding,))


def test_restricted_worker_callbacks_input_state_logs_and_clean_stop(qtbot):
    scene = scripted("""def start(ctx):
    ctx.state["started"] = True
    print("started")

def on_key(ctx, key, pressed):
    if pressed and key == "space":
        ctx.add_score(7)

def on_collect(ctx, other):
    print("collected " + other)

def update(ctx, dt):
    assert ctx.state["started"]
    ctx.move(ctx.input.horizontal * 120 * dt, 0)

def stop(ctx):
    print("stopped")
""")
    host = ScriptHost(scene)
    results, faults = [], []
    host.result.connect(results.append)
    host.fault.connect(faults.append)
    host.start()
    qtbot.waitUntil(lambda: host.ready or host.failed, timeout=6000)
    try:
        assert not faults
        assert results[0].logs == ("started",)
        assert host.step(
            0.05,
            1.0,
            ["d", "space"],
            {"player": (100, 100)},
            [
                {"entity_id": "player", "kind": "collect", "other": "coin"},
            ],
        )
        qtbot.waitUntil(lambda: len(results) == 2)
        assert [action.kind for action in results[1].actions] == ["score", "move"]
        assert results[1].actions[-1].values == (6.0, 0.0)
        assert results[1].logs == ("collected coin",)
        host.stop()
        qtbot.waitUntil(lambda: not host.active)
        assert results[-1].logs == ("stopped",)
        assert not faults
    finally:
        host.stop()
        qtbot.waitUntil(lambda: not host.active)
    assert scene.entity("player").x == 100


@pytest.mark.parametrize(
    "source, message, line",
    [
        ("def start(ctx):\n    1 / 0\n", "ZeroDivisionError", 2),
        ("def start(:\n", "SyntaxError", 1),
        ("def update(ctx, dt):\n    while True: pass\n", "deadline", 0),
        ("import os\ndef start(ctx):\n    os.write(1, b'x' * 70000)\n", "response", 0),
    ],
)
def test_worker_failures_are_bounded_and_identify_source(qtbot, source, message, line):
    scene = scripted(source)
    host = ScriptHost(scene)
    faults = []
    host.fault.connect(faults.append)
    host.start()
    qtbot.waitUntil(lambda: host.ready or host.failed, timeout=6000)
    if not host.failed:
        host.step(0.02, 0.02, [], {"player": (100, 100)}, [])
    qtbot.waitUntil(lambda: bool(faults), timeout=6000)
    qtbot.waitUntil(lambda: not host.active)
    assert faults[0].path == scene.scripts[0].path
    assert message in faults[0].message
    assert faults[0].line == line


def test_worker_does_not_inherit_editor_credentials_or_import_paths(qtbot, tmp_path, monkeypatch):
    private = tmp_path / "credential"
    private.write_text("private")
    monkeypatch.setenv("SOLAR_TEST_SECRET", "private")
    source = f"""import os
import math

def start(ctx):
    assert "SOLAR_TEST_SECRET" not in os.environ
    assert math.sqrt(9) == 3
    try:
        open({str(private)!r}).read()
    except PermissionError:
        pass
    else:
        raise AssertionError("credential accessible")
    try:
        import solar_forge_engine.editor
    except ImportError:
        pass
    else:
        raise AssertionError("editor accessible")
    ctx.move(1, 0)
"""
    host = ScriptHost(scripted(source))
    results, faults = [], []
    host.result.connect(results.append)
    host.fault.connect(faults.append)
    host.start()
    qtbot.waitUntil(lambda: host.ready or host.failed, timeout=6000)
    try:
        assert not faults
        assert results[0].actions[0].values == (1.0, 0.0)
    finally:
        host.stop()
        qtbot.waitUntil(lambda: not host.active)
    assert private.read_text() == "private"


def test_player_scripts_move_collect_collide_pause_restart_and_preserve_scene(qtbot):
    from PySide6.QtCore import Qt

    from solar_forge_engine.core.scene import Role
    from solar_forge_engine.runtime.player import PlayerWindow

    source = """def start(ctx):
    ctx.state["hits"] = 0
    ctx.set_color("#abcdef")
    ctx.set_rotation(15)

def on_collect(ctx, other):
    ctx.add_score(10)

def on_collision(ctx, other):
    ctx.state["hits"] += 1
    ctx.add_score(1)

def update(ctx, dt):
    ctx.move(ctx.input.horizontal * 240 * dt, 0)
"""
    scene = scripted(source)
    scene = replace(
        scene,
        entities=(
            Entity("player", x=100, y=100, role=Role.PLAYER),
            Entity("coin", x=110, y=100, role=Role.COIN),
            Entity("wall", x=190, y=0, width=2, height=576, role=Role.WALL),
        ),
    )
    player = PlayerWindow(scene, "player")
    qtbot.addWidget(player)
    player.show()
    qtbot.waitUntil(lambda: player.script_host.ready)
    qtbot.waitUntil(player.isActiveWindow)
    qtbot.keyPress(player, Qt.Key.Key_D)
    qtbot.waitUntil(lambda: player.simulation.score > 10, timeout=3000)
    qtbot.keyRelease(player, Qt.Key.Key_D)
    assert player.simulation.x == 126
    assert player.simulation.collected == {"coin"}
    assert player.items["player"].rotation() == 15
    assert scene.entity("player").color != "#abcdef"
    player.toggle_pause()
    paused_x = player.simulation.x
    qtbot.wait(40)
    assert player.simulation.x == paused_x
    old_host = player.script_host
    old_exits = []
    old_host.finished.connect(lambda: old_exits.append(True))
    player.restart()
    qtbot.waitUntil(lambda: player.script_host is not old_host and player.script_host.ready)
    assert old_exits
    assert player.simulation.x == 100
    assert player.simulation.scene == scene
    new_host = player.script_host
    player.close()
    qtbot.waitUntil(lambda: not new_host.active)
    assert not player.isVisible()
