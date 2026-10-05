import base64
import json

import pytest
from PySide6.QtCore import Qt

from solar_forge_engine.core.commands import Document, SetEntity
from solar_forge_engine.core.scene import Entity, InputPreset, Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.cleanup import plan_cleanup
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.project.workspace import create_project, open_project
from solar_forge_engine.runtime.player import PlayerWindow
from solar_forge_engine.runtime.simulation import Simulation


@pytest.mark.parametrize(
    "changes",
    [
        {"move_speed": -1},
        {"move_speed": 2001},
        {"move_speed": True},
        {"move_speed": float("nan")},
        {"input_preset": "exec"},
    ],
)
def test_invalid_settings_leave_history_and_scene_unchanged(changes):
    document = Document(Scene(entities=(Entity("player"),)))
    original = document.scene
    with pytest.raises(ValueError):
        document.execute(SetEntity("player", changes), expected_revision=0)
    assert document.scene == original
    assert document.revision == 0
    assert not document.can_undo


@pytest.mark.parametrize("version", [3, 4])
def test_legacy_movement_defaults_upgrade_backups_and_cleanup(tmp_path, version):
    sprite = Sprite(1, 1, base64.b64encode(bytes([20, 30, 40, 255])).decode())
    scene = Scene(entities=(Entity("player", sprite=sprite),))
    project = create_project(tmp_path / "Game", scene)
    path = project.scene_path()
    data = scene.to_data() if version == 3 else json.loads(path.read_bytes())
    data["format_version"] = version
    for entry in data["entities"]:
        del entry["move_speed"]
        del entry["input_preset"]
    original = json.dumps(data).encode()
    path.write_bytes(original)
    assert open_project(project.root)[1] == scene
    save_project_scene(project.root, path, scene)
    assert path.with_name(f"{path.name}.v{version}.bak").read_bytes() == original
    assert open_project(project.root)[1] == scene
    assert not plan_cleanup(project, set()).candidates
    path.write_bytes(original)
    with pytest.raises(ValueError, match="backup already exists"):
        save_project_scene(project.root, path, scene)
    assert path.read_bytes() == original


def test_editor_apply_undo_duplicate_and_portable_settings(qtbot, tmp_path):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    original = editor.document.scene
    editor.speed_field.setValue(120)
    editor.input_field.setCurrentIndex(editor.input_field.findData(InputPreset.ARROWS.value))
    editor.apply_inspector()
    edited = editor.document.scene
    entity = edited.entities[0]
    assert (entity.move_speed, entity.input_preset) == (120, InputPreset.ARROWS)
    editor.document.undo()
    editor.refresh()
    assert editor.document.scene == original
    assert editor.speed_field.value() == 240
    editor.document.redo()
    editor.refresh()
    editor.duplicate_selected()
    assert editor.document.scene.entities[-1].move_speed == 120
    assert editor.document.scene.entities[-1].input_preset == InputPreset.ARROWS
    path = tmp_path / "movement.forge.json"
    save_scene(path, editor.document.scene)
    assert load_scene(path) == editor.document.scene
    project = create_project(tmp_path / "Game", editor.document.scene)
    assert open_project(project.root)[1] == editor.document.scene
    editor.saved_scene = editor.document.scene


@pytest.mark.parametrize(
    "preset,accepted,rejected",
    [
        (InputPreset.WASD, Qt.Key.Key_D, Qt.Key.Key_Right),
        (InputPreset.ARROWS, Qt.Key.Key_Right, Qt.Key.Key_D),
    ],
)
def test_player_uses_speed_and_selected_keys_after_restart(qtbot, preset, accepted, rejected):
    scene = Scene(entities=(Entity("player", x=100, y=100, move_speed=120, input_preset=preset),))
    player = PlayerWindow(scene, "player")
    qtbot.addWidget(player)
    player.timer.stop()
    qtbot.keyPress(player, rejected)
    assert not player.keys
    qtbot.keyPress(player, accepted)
    assert player.keys == {accepted}
    player.simulation.step(1, 1, 0.1)
    assert (
        (player.simulation.x - 100) ** 2 + (player.simulation.y - 100) ** 2
    ) ** 0.5 == pytest.approx(12)
    player.restart()
    assert not player.keys
    assert player.simulation.speed == 120
    assert player.simulation.x == 100
    qtbot.keyPress(player, accepted)
    assert player.keys == {accepted}
    still = Simulation(Scene(entities=(Entity("still", move_speed=0),)), "still")
    still.step(1, 1)
    assert (still.x, still.y) == (0, 0)
    assert scene.entity("player").x == 100
