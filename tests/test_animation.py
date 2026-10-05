import base64
import hashlib
import json
from dataclasses import asdict

import pytest

from solar_forge_engine.core.animation import Animation
from solar_forge_engine.core.commands import Document, SetEntity
from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.cleanup import plan_cleanup
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.project.workspace import create_project, open_project
from solar_forge_engine.runtime.player import PlayerWindow


def sheet():
    return Sprite(2, 1, base64.b64encode(bytes([255, 0, 0, 255, 0, 255, 0, 255])).decode())


@pytest.mark.parametrize(
    "settings",
    [
        {"columns": 3, "rows": 1, "fps": 8},
        {"columns": True, "rows": 1, "fps": 8},
        {"columns": 1, "rows": 1, "fps": 0},
        {"columns": 1, "rows": 1, "fps": 61},
        {"columns": 256, "rows": 256, "fps": 8},
    ],
)
def test_bad_animation_commands_leave_history_unchanged(settings):
    document = Document(Scene(entities=(Entity("sprite", sprite=sheet()),)))
    original = document.scene
    with pytest.raises(ValueError):
        document.execute(SetEntity("sprite", {"animation": settings}), expected_revision=0)
    assert document.scene == original
    assert document.revision == 0
    assert not document.can_undo


def test_animation_requires_sprite_and_editor_edits_are_undoable(qtbot, tmp_path):
    with pytest.raises(ValueError, match="requires a sprite"):
        Entity("empty", animation=Animation())
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor._confirm_discard = lambda: True
    editor.add_rectangle()
    editor.execute(SetEntity(editor.selected_id, {"sprite": asdict(sheet())}))
    original = editor.document.scene
    editor.animation_check.setChecked(True)
    editor.animation_fields["columns"].setValue(2)
    editor.animation_fields["fps"].setValue(10)
    editor.apply_inspector()
    edited = editor.document.scene
    assert edited.entities[0].animation == Animation(2, 1, 10)
    editor.undo()
    assert editor.document.scene == original
    editor.redo()
    assert editor.document.scene == edited
    editor.duplicate_selected()
    assert editor.document.scene.entities[-1].animation == Animation(2, 1, 10)
    editor.clear_sprite()
    assert editor.document.scene.entities[-1].animation is None
    editor.undo()
    path = tmp_path / "animation.forge.json"
    save_scene(path, editor.document.scene)
    assert load_scene(path) == editor.document.scene
    project = create_project(tmp_path / "Game", editor.document.scene)
    assert open_project(project.root)[1] == editor.document.scene
    assert len(list((project.root / "assets").iterdir())) == 1


@pytest.mark.parametrize("version", [5, 6])
def test_animation_upgrade_preserves_legacy_bytes_and_cleanup(tmp_path, version):
    scene = Scene(entities=(Entity("sprite", sprite=sheet()),))
    project = create_project(tmp_path / "Game", scene)
    path = project.scene_path()
    data = scene.to_data() if version == 5 else json.loads(path.read_bytes())
    data["format_version"] = version
    for entry in data["entities"]:
        del entry["animation"]
    original = json.dumps(data).encode()
    path.write_bytes(original)
    assert open_project(project.root)[1] == scene
    save_project_scene(project.root, path, scene)
    assert path.with_name(f"{path.name}.v{version}.bak").read_bytes() == original
    assert not plan_cleanup(project, set()).candidates


def test_player_frame_timing_pause_restart_and_authored_geometry(qtbot, monkeypatch):
    scene = Scene(
        entities=(Entity("sprite", x=100, y=100, sprite=sheet(), animation=Animation(2, 1, 10)),)
    )
    player = PlayerWindow(scene, "sprite")
    qtbot.addWidget(player)
    player.timer.stop()
    item = player.items["sprite"]

    def color():
        return item.pixmap().toImage().pixelColor(0, 0).name()

    assert color() == "#ff0000"
    assert item.sceneBoundingRect().width() == pytest.approx(64)
    monkeypatch.setattr(player, "isActiveWindow", lambda: True)
    player._last_tick = 0
    monkeypatch.setattr("solar_forge_engine.runtime.player.time.monotonic", lambda: 0.1)
    player.tick()
    assert player._ticks == 6
    assert color() == "#00ff00"
    player._ticks = 12
    player._sync_position()
    assert color() == "#ff0000"
    player.toggle_pause()
    monkeypatch.setattr(
        "solar_forge_engine.runtime.player.time.monotonic", lambda: player._last_tick + 0.1
    )
    player.tick()
    assert player._ticks == 12
    player.restart()
    assert player._ticks == 0
    assert color() == "#ff0000"
    assert player.simulation.scene == scene


def test_previous_release_recovery_survives_animation_format_upgrade(tmp_path):
    from dataclasses import replace

    from solar_forge_engine.project.recovery import read_recovery, recovery_path

    baseline = Scene.from_data(Scene(entities=(Entity("sprite", sprite=sheet()),)).to_data())
    project = create_project(tmp_path / "Game", baseline)

    def legacy(scene):
        data = scene.to_data()
        data["format_version"] = 5
        for entry in data["entities"]:
            del entry["animation"]
        return data

    edited = replace(baseline, name="Recovered")
    envelope = {
        "format_version": 1,
        "base_hash": hashlib.sha256(
            json.dumps(legacy(baseline), sort_keys=True).encode()
        ).hexdigest(),
        "scene": legacy(edited),
    }
    path = recovery_path(project)
    path.write_text(json.dumps(envelope))
    assert read_recovery(project, baseline) == edited
    changed = Scene(entities=(Entity("sprite", sprite=sheet(), animation=Animation(2, 1, 10)),))
    with pytest.raises(ValueError, match="older saved scene"):
        read_recovery(project, changed)
    assert path.exists()
    envelope["base_hash"] = {}
    path.write_text(json.dumps(envelope))
    with pytest.raises(ValueError, match="older saved scene"):
        read_recovery(project, baseline)
