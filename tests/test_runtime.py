import math

import pytest
from PySide6.QtCore import QProcess, Qt

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.runtime.player import PlayerWindow
from solar_forge_engine.runtime.simulation import FIXED_STEP, Simulation


def test_movement_is_normalized_bounded_and_separate_from_authoring():
    scene = Scene(entities=(Entity("player", x=100, y=100),))
    simulation = Simulation(scene, "player")
    simulation.step(1, 1)
    assert math.hypot(simulation.x - 100, simulation.y - 100) == pytest.approx(240 * FIXED_STEP)
    for _ in range(1000):
        simulation.step(1, 1)
    assert (simulation.x, simulation.y) == (1024 - 64, 576 - 64)
    assert scene.entity("player").x == 100


def test_player_keyboard_ticks_pause_and_restart(qtbot):
    player = PlayerWindow(Scene(entities=(Entity("player", x=100, y=100),)), "player")
    qtbot.addWidget(player)
    player.show()
    qtbot.waitUntil(player.isActiveWindow)
    qtbot.keyPress(player, Qt.Key.Key_D)
    assert Qt.Key.Key_D in player.keys
    qtbot.waitUntil(lambda: player.simulation.x > 100)
    qtbot.keyRelease(player, Qt.Key.Key_D)
    assert not player.keys
    player.simulation.step(1, 0)
    assert player.simulation.x > 100
    player.toggle_pause()
    assert player.paused
    assert player.pause_button.text() == "Resume"
    player.restart()
    assert not player.paused
    assert player.simulation.x == 100
    assert player.items["player"].pos().x() == 100


def test_editor_starts_snapshot_without_importing_project_code_or_mutating_scene(qtbot, tmp_path):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    shadow_package = tmp_path / "solar_forge_engine"
    shadow_package.mkdir()
    (shadow_package / "__init__.py").write_text('raise RuntimeError("Project code must not run")')
    editor.preview.setWorkingDirectory(str(tmp_path))
    original = editor.document.scene
    revision = editor.document.revision
    editor.play()
    assert editor.preview.waitForStarted(5000)
    qtbot.waitUntil(lambda: "Preview ready" in editor.log.toPlainText(), timeout=5000)
    editor.stop_preview()
    assert editor.preview.waitForFinished(5000)
    assert editor.preview.state() == QProcess.ProcessState.NotRunning
    assert editor.document.scene == original
    assert editor.document.revision == revision
    editor.saved_scene = original


def test_game_text_is_plain(qtbot, tmp_path):
    from PySide6.QtGui import QColor, QImage

    private = QImage(8, 8, QImage.Format.Format_RGB32)
    private.fill(QColor("#ff00ff"))
    path = tmp_path / "p.png"
    assert private.save(str(path))
    name = f"<img src='{path}'>"
    player = PlayerWindow(Scene(entities=(Entity("player", name=name),)), "player")
    qtbot.addWidget(player)
    player.timer.stop()
    label = player.controls_label
    label.resize(600, 40)
    painted = QImage(label.size(), QImage.Format.Format_RGB32)
    painted.fill(QColor("black"))
    label.render(painted)
    assert not any(
        painted.pixelColor(x, y) == QColor("#ff00ff")
        for x in range(painted.width())
        for y in range(painted.height())
    )
    assert name in label.text()
    player.close()
