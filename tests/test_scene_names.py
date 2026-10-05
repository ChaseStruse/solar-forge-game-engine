from PySide6.QtWidgets import QInputDialog

from solar_forge_engine.core.commands import SetSceneName
from solar_forge_engine.core.scene import Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.workspace import create_project, open_project


def test_scene_rename_undo_and_save_keep_project_paths_and_startup(tmp_path, qtbot, monkeypatch):
    project = create_project(tmp_path / "Game", Scene())
    manifest = (project.root / "project.json").read_bytes()
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(project.root)
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Solar meadow", True))
    editor.rename_scene()
    assert editor.document.scene.name == "Solar meadow"
    assert editor.path == project.scene_path()
    assert editor.dirty
    editor.undo()
    assert editor.document.scene.name == "Untitled scene"
    editor.redo()
    assert editor.save()
    assert open_project(project.root)[1].name == "Solar meadow"
    assert (project.root / "project.json").read_bytes() == manifest
    errors = []
    monkeypatch.setattr(editor, "_error", errors.append)
    revision = editor.document.revision
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("", True))
    editor.rename_scene()
    assert errors and editor.document.revision == revision and not editor.dirty
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("Cancelled", False))
    editor.rename_scene()
    assert not editor.dirty
    editor.close()


def test_rename_does_not_overwrite_edits_made_during_dialog(qtbot, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    errors = []
    monkeypatch.setattr(editor, "_error", errors.append)

    def expired(*args, **kwargs):
        editor.execute(SetSceneName("Current title"))
        return "Old proposal", True

    monkeypatch.setattr(QInputDialog, "getText", expired)
    editor.rename_scene()
    assert editor.document.scene.name == "Current title"
    assert errors and "scene changed" in errors[-1]
    editor.undo()
    editor.close()
