from dataclasses import replace
from threading import Event

import pytest

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.recovery import read_recovery, recovery_path, write_recovery
from solar_forge_engine.project.workspace import create_project


def test_recovery_is_atomic_self_contained_and_rejects_stale_baseline(tmp_path, monkeypatch):
    baseline = Scene(entities=(Entity("player"),))
    project = create_project(tmp_path / "Game", baseline)
    edited = replace(baseline, name="Recovered")
    saved_bytes = project.scene_path().read_bytes()
    write_recovery(project, edited, baseline)
    snapshot = recovery_path(project).read_bytes()
    assert read_recovery(project, baseline) == edited
    assert project.scene_path().read_bytes() == saved_bytes
    with pytest.raises(ValueError, match="older saved"):
        read_recovery(project, edited)

    def fail_replace(*args):
        raise OSError("disk full")

    monkeypatch.setattr("solar_forge_engine.project.storage.os.replace", fail_replace)
    with pytest.raises(OSError):
        write_recovery(project, replace(edited, name="Another"), baseline)
    assert recovery_path(project).read_bytes() == snapshot
    assert project.scene_path().read_bytes() == saved_bytes


def test_editor_autosaves_restores_undoes_and_clears_on_manual_save(qtbot, tmp_path, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    monkeypatch.setattr(editor, "_confirm_discard", lambda: True)
    editor.add_rectangle()
    root = tmp_path / "Game"
    assert editor.create_workspace(root)
    project = editor.project
    original = editor.document.scene
    original_bytes = editor.path.read_bytes()
    editor.numbers["x"].setValue(300)
    editor.apply_inspector()
    edited = editor.document.scene
    editor.recovery_timer.setInterval(10)
    editor.recovery_timer.start()
    qtbot.waitUntil(lambda: editor._recovery_job is None and recovery_path(project).exists())
    assert read_recovery(project, original) == edited
    assert editor.path.read_bytes() == original_bytes
    recovered = EditorWindow()
    qtbot.addWidget(recovered)
    monkeypatch.setattr(recovered, "_confirm_discard", lambda: True)
    monkeypatch.setattr(recovered, "_choose_recovery", lambda: "recover")
    assert recovered.load_workspace(root)
    assert recovered.dirty
    assert recovered.document.scene == edited
    recovered.undo()
    assert recovered.document.scene == original
    assert not recovery_path(project).exists()
    recovered.redo()
    assert recovered.save()
    assert not recovered.dirty
    assert not recovery_path(project).exists()
    editor.recovery_timer.stop()
    editor.saved_scene = edited


@pytest.mark.parametrize("choice", ["keep", "discard"])
def test_open_saved_scene_recovery_choices(qtbot, tmp_path, monkeypatch, choice):
    baseline = Scene()
    project = create_project(tmp_path / "Game", baseline)
    write_recovery(project, Scene(name="Unsaved"), baseline)
    editor = EditorWindow()
    qtbot.addWidget(editor)
    monkeypatch.setattr(editor, "_choose_recovery", lambda: choice)
    assert editor.load_workspace(project.root)
    assert editor.document.scene == baseline
    assert not editor.dirty
    assert recovery_path(project).exists() == (choice == "keep")


def test_inflight_autosave_cannot_reappear_after_manual_save(qtbot, tmp_path, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    monkeypatch.setattr(editor, "_confirm_discard", lambda: True)
    editor.add_rectangle()
    assert editor.create_workspace(tmp_path / "Game")
    editor.numbers["x"].setValue(300)
    editor.apply_inspector()
    started = Event()
    proceed = Event()
    actual_write = write_recovery

    def delayed_write(*args):
        started.set()
        assert proceed.wait(3)
        actual_write(*args)

    monkeypatch.setattr("solar_forge_engine.editor.recovery.write_recovery", delayed_write)
    editor.autosave()
    qtbot.waitUntil(started.is_set)
    try:
        assert editor.save()
    finally:
        proceed.set()
    qtbot.waitUntil(lambda: editor._recovery_job is None)
    assert not recovery_path(editor.project).exists()
    assert not editor.dirty


def test_bad_recovery_is_retained_without_blocking_saved_project(qtbot, tmp_path):
    project = create_project(tmp_path / "Game", Scene())
    path = recovery_path(project)
    path.write_bytes(b"invalid json")
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(project.root)
    assert editor.document.scene == Scene()
    assert path.read_bytes() == b"invalid json"
    assert "Recovery snapshot unavailable" in editor.log.toPlainText()


def test_explicit_discard_clears_snapshot_without_saving_edits(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    assert editor.create_workspace(tmp_path / "Game")
    project = editor.project
    saved_bytes = editor.path.read_bytes()
    editor.numbers["x"].setValue(400)
    editor.apply_inspector()
    editor.autosave()
    qtbot.waitUntil(lambda: editor._recovery_job is None)
    assert recovery_path(project).exists()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Discard)
    editor.new_scene()
    assert not recovery_path(project).exists()
    assert project.scene_path().read_bytes() == saved_bytes
    assert not editor.recovery_timer.isActive()


def test_autosave_failure_keeps_edits_and_manual_save_working(qtbot, tmp_path, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    assert editor.create_workspace(tmp_path / "Game")
    saved_bytes = editor.path.read_bytes()
    editor.numbers["x"].setValue(400)
    editor.apply_inspector()

    def fail_write(*args):
        raise OSError("snapshot storage unavailable")

    monkeypatch.setattr("solar_forge_engine.editor.recovery.write_recovery", fail_write)
    editor.autosave()
    qtbot.waitUntil(lambda: editor._recovery_job is None)
    assert editor.dirty
    assert editor.path.read_bytes() == saved_bytes
    assert "Autosave failed" in editor.log.toPlainText()
    assert editor.save()
    assert not editor.dirty
