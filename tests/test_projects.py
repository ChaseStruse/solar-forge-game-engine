import json

import pytest

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.workspace import create_project, open_project


def test_project_creation_edit_save_reopen_preserves_original_scene(qtbot, tmp_path, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    original_path = tmp_path / "original.forge.json"
    editor.path = original_path
    assert editor.save()
    original_bytes = original_path.read_bytes()
    editor.name_field.setText("My player")
    editor.apply_inspector()
    root = tmp_path / "My Game"
    assert editor.create_workspace(root)
    assert original_path.read_bytes() == original_bytes
    assert not editor.dirty
    assert (root / "assets").is_dir()
    assert "My Game" in editor.windowTitle()
    editor.numbers["x"].setValue(200)
    editor.apply_inspector()
    assert editor.save()
    reopened = EditorWindow()
    qtbot.addWidget(reopened)
    assert reopened.load_workspace(root)
    assert reopened.document.scene == editor.document.scene
    assert reopened.document.scene.entities[0].x == 200
    assert not reopened.dirty
    assert not reopened.document.can_undo
    project_bytes = reopened.path.read_bytes()
    reopened.add_rectangle()
    exported = tmp_path / "standalone.forge.json"
    monkeypatch.setattr(
        "solar_forge_engine.editor.window.QFileDialog.getSaveFileName",
        lambda *args: (str(exported), ""),
    )
    assert reopened.save(choose_path=True)
    assert reopened.project is None
    assert reopened.path == exported
    assert editor.path.read_bytes() == project_bytes
    assert reopened.load_workspace(root)
    reopened.new_scene()
    assert reopened.project is None
    assert reopened.path is None


def test_project_creation_refuses_existing_folder_and_rolls_back_failure(tmp_path, monkeypatch):
    existing = tmp_path / "existing"
    existing.mkdir()
    marker = existing / "keep.txt"
    marker.write_text("keep")
    with pytest.raises(FileExistsError):
        create_project(existing, Scene())
    assert marker.read_text() == "keep"

    def fail_save(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr("solar_forge_engine.project.workspace.save_project_scene", fail_save)
    root = tmp_path / "failed"
    with pytest.raises(OSError, match="disk unavailable"):
        create_project(root, Scene())
    assert not root.exists()


@pytest.mark.parametrize(
    "path",
    [
        "../outside.forge.json",
        "/tmp/outside.forge.json",
        "scenes/../outside.forge.json",
        "scenes//main.forge.json",
        "scenes\\main.forge.json",
    ],
)
def test_project_rejects_manifest_path_escape(tmp_path, path):
    root = tmp_path / "project"
    create_project(root, Scene())
    manifest = root / "project.json"
    data = json.loads(manifest.read_text())
    data["scene"] = path
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="relative file"):
        open_project(root)


def test_project_rejects_symlink_scene_and_keeps_editor_state(qtbot, tmp_path, monkeypatch):
    root = tmp_path / "project"
    create_project(root, Scene(entities=(Entity("object"),)))
    outside = tmp_path / "outside"
    (root / "scenes").rename(outside)
    (root / "scenes").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic links"):
        open_project(root)
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    original = editor.document.scene
    monkeypatch.setattr(editor, "_error", lambda message: None)
    assert not editor.load_workspace(root)
    assert editor.document.scene == original
    assert editor.project is None
    editor.saved_scene = original


def test_project_save_revalidates_path_before_writing(qtbot, tmp_path, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    root = tmp_path / "project"
    assert editor.create_workspace(root)
    scene_path = editor.path
    original = scene_path.read_bytes()
    outside = tmp_path / "outside.forge.json"
    scene_path.rename(outside)
    scene_path.symlink_to(outside)
    editor.numbers["x"].setValue(200)
    editor.apply_inspector()
    monkeypatch.setattr(editor, "_error", lambda message: None)
    assert not editor.save()
    assert outside.read_bytes() == original
    assert editor.dirty
    editor.saved_scene = editor.document.scene
