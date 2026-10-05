import base64
from pathlib import Path

import pytest
from PySide6.QtWidgets import QMessageBox

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.assets import save_project_scene, store_asset
from solar_forge_engine.project.cleanup import plan_cleanup, quarantine_assets, sprite_reference
from solar_forge_engine.project.recovery import read_recovery, write_recovery
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.project.workspace import create_project, open_project


def texture(color):
    return Sprite(1, 1, base64.b64encode(bytes([color, 0, 0, 255])).decode())


def store(project, sprite):
    path = project.root / sprite_reference(sprite)
    store_asset(path, base64.b64decode(sprite.pixels))
    return path


def test_cleanup_preserves_scene_backup_recovery_and_session_references(tmp_path):
    sprites = [texture(color) for color in range(5)]
    baseline = Scene(entities=(Entity("saved", sprite=sprites[0]),))
    project = create_project(tmp_path / "Game", baseline)
    paths = [store(project, sprite) for sprite in sprites]
    backup = project.scene_path().with_name("main.forge.json.v3.bak")
    backup_scene = Scene(entities=(Entity("backup", sprite=sprites[1]),))
    save_scene(backup, backup_scene)
    recovered = Scene(entities=(Entity("recovery", sprite=sprites[2]),))
    write_recovery(project, recovered, baseline)
    plan = plan_cleanup(project, {sprites[3]})
    assert plan.candidates == (sprite_reference(sprites[4]),)
    destination = quarantine_assets(project, {sprites[3]}, plan)
    assert not paths[4].exists()
    assert (destination / paths[4].name).read_bytes() == base64.b64decode(sprites[4].pixels)
    assert all(path.exists() for path in paths[:4])
    assert open_project(project.root)[1] == baseline
    assert read_recovery(project, baseline) == recovered
    assert load_scene(backup) == backup_scene


def test_cleanup_refuses_changes_after_review(tmp_path):
    project = create_project(tmp_path / "Game", Scene())
    sprite = texture(20)
    path = store(project, sprite)
    plan = plan_cleanup(project, set())
    save_project_scene(
        project.root, project.scene_path(), Scene(entities=(Entity("new", sprite=sprite),))
    )
    with pytest.raises(ValueError, match="changed after review"):
        quarantine_assets(project, set(), plan)
    assert path.exists()


@pytest.mark.parametrize("attack", ["invalid_recovery", "symlink", "budget"])
def test_cleanup_aborts_incomplete_scans(tmp_path, monkeypatch, attack):
    project = create_project(tmp_path / "Game", Scene())
    path = store(project, texture(30))
    if attack == "invalid_recovery":
        (project.root / "scenes/main.forge.json.recovery.json").write_bytes(b"invalid")
    elif attack == "symlink":
        (project.root / "scenes/linked").symlink_to(tmp_path, target_is_directory=True)
    else:
        monkeypatch.setattr("solar_forge_engine.project.cleanup.MAX_SCAN_BYTES", 1)
    with pytest.raises(ValueError):
        plan_cleanup(project, set())
    assert path.exists()
    assert not (project.root / ".asset-quarantine").exists()


def test_failed_quarantine_rolls_back_previous_moves(tmp_path, monkeypatch):
    project = create_project(tmp_path / "Game", Scene())
    paths = [store(project, texture(color)) for color in (40, 41)]
    plan = plan_cleanup(project, set())
    actual_rename = Path.rename
    count = 0

    def fail_second_move(source, target):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("move failed")
        return actual_rename(source, target)

    monkeypatch.setattr(Path, "rename", fail_second_move)
    with pytest.raises(OSError, match="move failed"):
        quarantine_assets(project, set(), plan)
    assert all(path.exists() for path in paths)


def test_native_cleanup_review_cancel_then_confirm(qtbot, tmp_path, monkeypatch):
    project = create_project(tmp_path / "Game", Scene())
    orphan = store(project, texture(50))
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(project.root)
    qtbot.waitUntil(lambda: editor._asset_index_job is None)
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Cancel)
    editor.review_unused_assets()
    qtbot.waitUntil(lambda: editor._cleanup_job is None)
    assert orphan.exists()
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Ok)
    editor.review_unused_assets()
    qtbot.waitUntil(lambda: editor._cleanup_job is None and not orphan.exists())
    assert editor.isEnabled()
    assert "quarantined" in editor.log.toPlainText()
    assert len(list((project.root / ".asset-quarantine").glob("*/*.rgba"))) == 1


def test_cleanup_scan_results_expire_when_editor_changes(qtbot, tmp_path, monkeypatch):
    from threading import Event

    from solar_forge_engine.project.cleanup import plan_cleanup as actual_scan

    project = create_project(tmp_path / "Game", Scene())
    orphan = store(project, texture(60))
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(project.root)
    qtbot.waitUntil(lambda: editor._asset_index_job is None)
    started, proceed = Event(), Event()

    def delayed_scan(*args):
        started.set()
        assert proceed.wait(3)
        return actual_scan(*args)

    monkeypatch.setattr("solar_forge_engine.editor.cleanup.plan_cleanup", delayed_scan)
    editor.review_unused_assets()
    qtbot.waitUntil(started.is_set)
    try:
        editor.add_rectangle()
    finally:
        proceed.set()
    qtbot.waitUntil(lambda: editor._cleanup_job is None)
    assert orphan.exists()
    assert "review expired" in editor.log.toPlainText()
    editor.saved_scene = editor.document.scene
