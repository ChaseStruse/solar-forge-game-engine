from dataclasses import replace

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.recovery import recovery_path, write_recovery
from solar_forge_engine.project.workspace import (
    create_project,
    create_scene,
    list_scenes,
    open_scene,
)


def test_scene_create_switch_save_cancel_and_per_scene_recovery(qtbot, tmp_path, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    assert editor.create_workspace(tmp_path / "Game")
    first = editor.project
    first_bytes = first.scene_path().read_bytes()
    assert editor.new_project_scene("Level 2")
    second = editor.project
    assert editor.project_scene_list.count() == 2
    assert editor.document.scene.name == "Level 2"
    editor.add_rectangle()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Cancel)
    dirty = editor.document.scene
    assert not editor.switch_project_scene(first.scene)
    assert editor.project == second
    assert editor.document.scene == dirty
    assert editor.project_scene_list.currentItem().data(Qt.ItemDataRole.UserRole) == second.scene
    assert editor.save()
    second_bytes = second.scene_path().read_bytes()
    assert editor.switch_project_scene(first.scene)
    assert editor.document.scene.entities
    assert editor.project == first
    assert editor.project.scene_path().read_bytes() == first_bytes
    assert second.scene_path().read_bytes() == second_bytes
    baseline = open_scene(first, first.scene)[1]
    write_recovery(first, replace(baseline, name="Recovered first"), baseline)
    assert editor.switch_project_scene(second.scene)
    monkeypatch.setattr(editor, "_choose_recovery", lambda: "recover")
    assert editor.switch_project_scene(first.scene)
    assert editor.dirty
    assert editor.document.scene.name == "Recovered first"
    assert recovery_path(first).exists()
    assert not recovery_path(second).exists()
    editor.undo()
    assert not editor.dirty
    assert not recovery_path(first).exists()


@pytest.mark.parametrize("name", ["../outside", "Level/2", "", "x" * 65, "main"])
def test_invalid_scene_creation_preserves_files(qtbot, tmp_path, monkeypatch, name):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.create_workspace(tmp_path / "Game")
    original = editor.path.read_bytes()
    monkeypatch.setattr(editor, "_error", lambda message: None)
    monkeypatch.setattr(
        editor, "_confirm_discard", lambda: pytest.fail("Invalid scene must not discard")
    )
    assert not editor.new_project_scene(name)
    assert editor.path.read_bytes() == original
    assert len(list_scenes(editor.project)) == 1
    monkeypatch.setattr(editor, "_confirm_discard", lambda: True)


def test_scene_creation_failure_and_symlink_switch_preserve_project(tmp_path, monkeypatch):
    project = create_project(tmp_path / "Game", Scene())
    original = project.scene_path().read_bytes()

    def fail_link(*args):
        raise OSError("disk full")

    monkeypatch.setattr("solar_forge_engine.project.storage.os.link", fail_link)
    with pytest.raises(OSError, match="disk full"):
        create_scene(project, "Failed")
    assert list_scenes(project) == [project.scene]
    assert project.scene_path().read_bytes() == original
    outside = tmp_path / "outside.forge.json"
    outside.write_bytes(original)
    (project.root / "scenes/linked.forge.json").symlink_to(outside)
    with pytest.raises(ValueError, match="symbolic links"):
        open_scene(project, "scenes/linked.forge.json")
