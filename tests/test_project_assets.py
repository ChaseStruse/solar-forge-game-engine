import base64
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QProcess

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.project.workspace import create_project, open_project


def textured_scene():
    sprite = Sprite(2, 1, base64.b64encode(bytes([255, 0, 0, 255, 0, 0, 0, 0])).decode())
    return Scene(entities=(Entity("player", sprite=sprite), Entity("copy", sprite=sprite)))


def test_shared_project_assets_survive_move_and_play_and_standalone_save(qtbot, tmp_path):
    scene = textured_scene()
    root = tmp_path / "project"
    project = create_project(root, scene)
    disk = json.loads(project.scene_path().read_bytes())
    assert disk["format_version"] == 10
    assert len(list((root / "assets").iterdir())) == 1
    reference = disk["entities"][0]["sprite"]["asset"]
    assert reference.startswith("assets/")
    assert "pixels" not in disk["entities"][0]["sprite"]
    assert disk["entities"][1]["sprite"]["asset"] == reference
    moved = tmp_path / "moved"
    root.rename(moved)
    project, reopened = open_project(moved)
    assert reopened == scene
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(moved)
    editor.play()
    assert editor.preview.waitForStarted(5000)
    qtbot.waitUntil(lambda: "Preview ready" in editor.log.toPlainText(), timeout=5000)
    editor.stop_preview()
    assert editor.preview.waitForFinished(5000)
    assert editor.preview.state() == QProcess.ProcessState.NotRunning
    standalone = tmp_path / "standalone.forge.json"
    save_scene(standalone, reopened)
    (moved / reference).unlink()
    assert load_scene(standalone) == scene
    with pytest.raises(ValueError, match="Open project"):
        load_scene(project.scene_path())


@pytest.mark.parametrize("attack", ["traversal", "symlink", "missing", "damaged"])
def test_invalid_project_asset_cannot_replace_editor_state(tmp_path, qtbot, monkeypatch, attack):
    root = tmp_path / "project"
    project = create_project(root, textured_scene())
    data = json.loads(project.scene_path().read_bytes())
    reference = data["entities"][0]["sprite"]["asset"]
    asset = root / reference
    if attack == "traversal":
        data["entities"][0]["sprite"]["asset"] = "../outside.rgba"
        project.scene_path().write_text(json.dumps(data))
    elif attack == "symlink":
        outside = tmp_path / "outside.rgba"
        asset.rename(outside)
        asset.symlink_to(outside)
    elif attack == "missing":
        asset.unlink()
    else:
        asset.write_bytes(b"\x00" * 8)
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    previous = editor.document.scene
    monkeypatch.setattr(editor, "_error", lambda message: None)
    assert not editor.load_workspace(root)
    assert editor.document.scene == previous
    assert editor.project is None
    editor.saved_scene = previous


def test_asset_save_failure_preserves_previous_scene_and_references(tmp_path, monkeypatch):
    root = tmp_path / "project"
    original = Scene(entities=(Entity("rectangle"),))
    project = create_project(root, original)
    previous = project.scene_path().read_bytes()

    def fail_replace(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("solar_forge_engine.project.storage.os.replace", fail_replace)
    with pytest.raises(OSError, match="disk unavailable"):
        save_project_scene(root, project.scene_path(), textured_scene())
    assert project.scene_path().read_bytes() == previous
    assert open_project(root)[1] == original
    assert len(list((root / "assets").iterdir())) == 1


def test_embedded_project_scene_upgrade_preserves_original_bytes(tmp_path):
    root = tmp_path / "project"
    project = create_project(root, Scene())
    original = textured_scene()
    save_scene(project.scene_path(), original)
    previous = project.scene_path().read_bytes()
    assert json.loads(previous)["format_version"] == 9
    assert open_project(root)[1] == original
    save_project_scene(root, project.scene_path(), original)
    backup = project.scene_path().with_name(project.scene_path().name + ".v9.bak")
    assert backup.read_bytes() == previous
    assert open_project(root)[1] == original


@pytest.mark.parametrize("kind", ["fifo", "symlink"])
def test_sprite_reader_rejects_unsafe_file_without_waiting(tmp_path, kind):
    path = tmp_path / "asset.rgba"
    if kind == "fifo":
        os.mkfifo(path)
    else:
        outside = tmp_path / "outside.rgba"
        outside.write_bytes(b"private bytes")
        path.symlink_to(outside)
    script = """
import sys
from pathlib import Path
from solar_forge_engine.project.assets import read_asset
try:
    read_asset(Path(sys.argv[1]))
except (OSError, ValueError):
    sys.exit(0)
sys.exit(1)
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", script, str(path)],
        capture_output=True,
        timeout=3,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("reuse", [False, True])
def test_sprite_directory_flush_precedes_scene_publication(tmp_path, monkeypatch, reuse):
    project = create_project(tmp_path / "Game", textured_scene() if reuse else Scene())
    flushed = []
    original = os.fsync

    def record(descriptor):
        flushed.append(Path(os.readlink(f"/proc/self/fd/{descriptor}")))
        original(descriptor)

    monkeypatch.setattr("solar_forge_engine.project.storage.os.fsync", record)
    save_project_scene(project.root, project.scene_path(), textured_scene())
    asset_directory_flush = flushed.index(project.root / "assets")
    scene_temporary_flush = next(
        index for index, path in enumerate(flushed) if path.parent == project.root / "scenes"
    )
    assert asset_directory_flush < scene_temporary_flush
    assert open_project(project.root)[1] == textured_scene()
