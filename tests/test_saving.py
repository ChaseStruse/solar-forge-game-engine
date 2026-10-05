import os
import stat
from threading import Event, get_ident

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFileDialog

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.editor import saving
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project import storage
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.storage import load_scene, save_scene
from solar_forge_engine.project.workspace import create_project


@pytest.mark.parametrize("project_mode", [False, True])
def test_external_changes_survive_manual_save_and_save_as_keeps_edits(
    tmp_path, qtbot, monkeypatch, project_mode
):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    if project_mode:
        project = create_project(tmp_path / "Game", Scene())
        assert editor.load_workspace(project.root)
    else:
        path = tmp_path / "scene.forge.json"
        save_scene(path, Scene())
        assert editor.load(path)
    editor.add_rectangle()
    edited = editor.document.scene
    assert editor.path is not None
    if project_mode:
        save_project_scene(project.root, editor.path, Scene("External edit"))
    else:
        save_scene(editor.path, Scene("External edit"))
    external = editor.path.read_bytes()
    errors = []
    monkeypatch.setattr(editor, "_error", errors.append)
    assert not editor.save()
    assert "changed externally" in errors[-1]
    assert editor.path.read_bytes() == external
    assert editor.document.scene == edited and editor.dirty
    destination = tmp_path / "My edits.forge.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(destination), ""))
    assert editor.save(choose_path=True)
    assert load_scene(destination) == edited
    assert not editor.dirty
    editor.close()


@pytest.mark.parametrize("replacement", ["removed", "fifo", "symlink"])
def test_replaced_scene_is_not_overwritten_or_followed(tmp_path, qtbot, monkeypatch, replacement):
    path = tmp_path / "scene.forge.json"
    save_scene(path, Scene())
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load(path)
    editor.add_rectangle()
    path.unlink()
    outside = tmp_path / "outside"
    outside.write_bytes(b"preserve me")
    if replacement == "fifo":
        os.mkfifo(path)
    elif replacement == "symlink":
        path.symlink_to(outside)
    errors = []
    monkeypatch.setattr(editor, "_error", errors.append)
    assert not editor.save()
    assert errors and editor.dirty
    assert outside.read_bytes() == b"preserve me"
    if replacement == "removed":
        assert not path.exists()
    elif replacement == "fifo":
        assert stat.S_ISFIFO(path.stat().st_mode)
    else:
        assert path.is_symlink()
    editor.undo()
    editor.close()


def test_observed_change_before_atomic_publication_preserves_external_file(
    tmp_path, qtbot, monkeypatch
):
    path = tmp_path / "scene.forge.json"
    save_scene(path, Scene())
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.load(path)
    editor.add_rectangle()
    original = storage.atomic_write
    external = b"external bytes"

    def changed(target, raw, **options):
        target.write_bytes(external)
        original(target, raw, **options)

    monkeypatch.setattr(storage, "atomic_write", changed)
    errors = []
    monkeypatch.setattr(editor, "_error", errors.append)
    assert not editor.save()
    assert "changed during saving" in errors[-1]
    assert path.read_bytes() == external
    assert not list(tmp_path.glob(".forge-*"))
    editor.undo()
    editor.close()


def test_save_worker_keeps_event_loop_responsive_and_close_waits(tmp_path, qtbot, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.show()
    editor.add_rectangle()
    editor.path = tmp_path / "scene.forge.json"
    release = Event()
    main_thread = get_ident()
    worker_threads = []
    original = saving.save_scene

    def held(*args, **kwargs):
        worker_threads.append(get_ident())
        if not release.wait(3):
            raise OSError("UI did not process its event loop during saving")
        original(*args, **kwargs)

    def heartbeat():
        assert editor._save_job is not None
        assert not editor.isEnabled()
        assert not editor.save()
        editor.close()
        assert editor.isVisible()
        release.set()

    monkeypatch.setattr(saving, "save_scene", held)
    QTimer.singleShot(0, heartbeat)
    assert editor.save()
    assert worker_threads and worker_threads[0] != main_thread
    assert editor.isEnabled() and not editor.dirty
    assert load_scene(editor.path) == editor.document.scene
    editor.close()


def test_atomic_publication_flushes_file_and_parent_directory(tmp_path, monkeypatch):
    flushed = []
    original = os.fsync

    def record(descriptor):
        flushed.append(os.fstat(descriptor).st_mode)
        original(descriptor)

    monkeypatch.setattr(storage.os, "fsync", record)
    save_scene(tmp_path / "scene.forge.json", Scene())
    assert any(stat.S_ISREG(mode) for mode in flushed)
    assert any(stat.S_ISDIR(mode) for mode in flushed)
