import json

import pytest
from PySide6.QtCore import Qt

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.workspace import (
    create_project,
    create_scene,
    open_project,
    read_project,
    set_startup_scene,
)


def project_with_scene(tmp_path):
    project = create_project(tmp_path / "Game", Scene(entities=(Entity("main"),)))
    target, scene = create_scene(project, "Level Two")
    return project, target, scene


def test_startup_selection_reopens_target_and_preserves_scene_bytes(tmp_path):
    project, target, scene = project_with_scene(tmp_path)
    original = project.scene_path().read_bytes()
    saved_target = target.scene_path().read_bytes()
    updated = set_startup_scene(project, target.scene, read_project(project.root))
    assert updated.scene == target.scene
    assert open_project(project.root) == (updated, scene)
    assert project.scene_path().read_bytes() == original
    assert target.scene_path().read_bytes() == saved_target
    assert updated.name == project.name


@pytest.mark.parametrize("invalid", ["traversal", "symlink", "malformed", "missing"])
def test_bad_startup_targets_preserve_manifest(tmp_path, invalid):
    project, target, scene = project_with_scene(tmp_path)
    manifest = project.root / "project.json"
    original = manifest.read_bytes()
    reference = target.scene
    if invalid == "traversal":
        reference = "scenes/../outside.forge.json"
    elif invalid == "symlink":
        target.scene_path().unlink()
        target.scene_path().symlink_to(project.scene_path())
    elif invalid == "malformed":
        target.scene_path().write_bytes(b"invalid")
    else:
        target.scene_path().unlink()
    with pytest.raises((OSError, ValueError)):
        set_startup_scene(project, reference, project)
    assert manifest.read_bytes() == original


def test_stale_settings_and_failed_atomic_write_preserve_manifest(tmp_path, monkeypatch):
    project, target, scene = project_with_scene(tmp_path)
    manifest = project.root / "project.json"
    data = json.loads(manifest.read_bytes())
    data["name"] = "External edit"
    manifest.write_text(json.dumps(data))
    original = manifest.read_bytes()
    with pytest.raises(ValueError, match="settings changed"):
        set_startup_scene(project, target.scene, project)
    assert manifest.read_bytes() == original

    def failed_replace(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("solar_forge_engine.project.storage.os.replace", failed_replace)
    with pytest.raises(OSError, match="disk unavailable"):
        set_startup_scene(project, target.scene, read_project(project.root))
    assert manifest.read_bytes() == original
    assert not list(project.root.glob(".forge-*"))


def test_editor_startup_update_keeps_active_dirty_scene_history_and_path(qtbot, tmp_path):
    project, target, scene = project_with_scene(tmp_path)
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor._confirm_discard = lambda: True
    assert editor.load_workspace(project.root)
    qtbot.waitUntil(lambda: editor._asset_index_job is None)
    editor.add_rectangle()
    original, revision, path = editor.document.scene, editor.document.revision, editor.path
    for i in range(editor.project_scene_list.count()):
        row = editor.project_scene_list.item(i)
        if row.data(Qt.ItemDataRole.UserRole) == target.scene:
            editor.project_scene_list.setCurrentItem(row)
    assert editor.startup_button.isEnabled()
    editor.set_selected_startup_scene()
    qtbot.waitUntil(lambda: editor._startup_job is None)
    assert editor.document.scene == original
    assert editor.document.revision == revision
    assert editor.document.can_undo
    assert editor.project == project
    assert editor.path == path
    assert editor.dirty
    assert editor.isEnabled()
    assert target.scene_path().name in editor.startup_label.text()
    assert open_project(project.root)[1] == scene
    assert editor.switch_project_scene(target.scene)
    qtbot.waitUntil(lambda: editor._asset_index_job is None)
    assert not editor.startup_button.isEnabled()
