import os
import stat
from dataclasses import replace
from threading import Event

import pytest

from solar_forge_engine.core.scene import Entity, Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project import recovery, storage
from solar_forge_engine.project.assets import save_project_scene
from solar_forge_engine.project.recovery import read_recovery, recovery_path, write_recovery
from solar_forge_engine.project.workspace import create_project


@pytest.mark.parametrize("operation", ["write", "clear"])
def test_recovery_cannot_change_during_manual_scene_publication(tmp_path, monkeypatch, operation):
    baseline = Scene()
    project = create_project(tmp_path / "Game", baseline)
    write_recovery(project, Scene("Earlier edit"), baseline)
    snapshot = recovery_path(project).read_bytes()
    saved = project.scene_path().read_bytes()
    original = storage.os.replace

    def held(source, target):
        if target == project.scene_path():
            with pytest.raises(ValueError, match="save is in progress"):
                if operation == "write":
                    write_recovery(project, Scene("Late edit"), baseline)
                else:
                    recovery.clear_recovery(project, baseline)
            assert recovery_path(project).read_bytes() == snapshot
            assert project.scene_path().read_bytes() == saved
        original(source, target)

    monkeypatch.setattr(storage.os, "replace", held)
    save_project_scene(project.root, project.scene_path(), Scene("Saved edit"))
    assert recovery_path(project).read_bytes() == snapshot
    with pytest.raises(ValueError, match="older saved"):
        read_recovery(project, Scene("Saved edit"))


@pytest.mark.parametrize("existing", [False, True])
def test_late_external_recovery_publication_is_preserved(tmp_path, monkeypatch, existing):
    baseline = Scene()
    project = create_project(tmp_path / "Game", baseline)
    if existing:
        write_recovery(project, Scene("First edit"), baseline)
    original = recovery.atomic_write
    external = b"externally written recovery"

    def changed(path, raw, **options):
        path.write_bytes(external)
        original(path, raw, **options)

    monkeypatch.setattr(recovery, "atomic_write", changed)
    with pytest.raises((ValueError, FileExistsError)):
        write_recovery(project, Scene("Later edit"), baseline)
    assert recovery_path(project).read_bytes() == external
    assert not list(project.scene_path().parent.glob(".forge-*"))


def test_recovery_removal_flushes_containing_directory(tmp_path, monkeypatch):
    baseline = Scene()
    project = create_project(tmp_path / "Game", baseline)
    write_recovery(project, Scene("Edit"), baseline)
    flushed = []
    original = os.fsync

    def record(descriptor):
        assert not recovery_path(project).exists()
        flushed.append(os.fstat(descriptor).st_mode)
        original(descriptor)

    monkeypatch.setattr(recovery.os, "fsync", record)
    recovery.clear_recovery(project, baseline)
    assert flushed and all(stat.S_ISDIR(mode) for mode in flushed)


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
    qtbot.waitUntil(lambda: recovered._recovery_job is None)
    assert not recovery_path(project).exists()
    recovered.redo()
    assert recovered.save()
    qtbot.waitUntil(lambda: recovered._recovery_job is None)
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
    qtbot.waitUntil(lambda: editor._recovery_job is None)
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


def test_corrupt_snapshot_survives_autosave_undo_and_manual_save(qtbot, tmp_path):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor._confirm_discard = lambda: True
    editor.add_rectangle()
    assert editor.create_workspace(tmp_path / "Game")
    path = recovery_path(editor.project)
    path.write_bytes(b"invalid json")
    editor.numbers["x"].setValue(400)
    editor.apply_inspector()
    editor.autosave()
    qtbot.waitUntil(lambda: editor._recovery_job is None)
    assert path.read_bytes() == b"invalid json"
    assert editor.dirty
    assert "Autosave failed" in editor.log.toPlainText()
    editor.undo()
    qtbot.waitUntil(lambda: editor._recovery_job is None)
    assert path.read_bytes() == b"invalid json"
    editor.redo()
    assert editor.save()
    qtbot.waitUntil(lambda: editor._recovery_job is None)
    assert not editor.dirty
    assert path.read_bytes() == b"invalid json"
    assert "Recovery retained" in editor.log.toPlainText()


def test_changed_saved_baseline_and_stale_snapshot_are_not_overwritten(tmp_path):
    from solar_forge_engine.project.assets import save_project_scene
    from solar_forge_engine.project.recovery import clear_recovery

    baseline = Scene()
    project = create_project(tmp_path / "Game", baseline)
    edit = Scene(name="Unsaved")
    write_recovery(project, edit, baseline)
    raw = recovery_path(project).read_bytes()
    external = Scene(name="External saved scene")
    save_project_scene(project.root, project.scene_path(), external)
    with pytest.raises(ValueError, match="changed externally"):
        write_recovery(project, edit, baseline)
    with pytest.raises(ValueError, match="older saved"):
        write_recovery(project, Scene(name="New edit"), external)
    with pytest.raises(ValueError, match="older saved"):
        clear_recovery(project, external)
    assert recovery_path(project).read_bytes() == raw
    assert project.scene_path().exists()


@pytest.mark.parametrize("kind", ["symlink", "fifo", "oversized"])
def test_recovery_rejects_unsafe_or_oversized_existing_snapshots(tmp_path, kind):
    import os

    from solar_forge_engine.project.recovery import clear_recovery
    from solar_forge_engine.project.storage import MAX_FILE_BYTES

    baseline = Scene()
    project = create_project(tmp_path / "Game", baseline)
    path = recovery_path(project)
    target = tmp_path / "target"
    target.write_bytes(b"keep")
    if kind == "symlink":
        path.symlink_to(target)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    for operation in (
        lambda: read_recovery(project, baseline),
        lambda: write_recovery(project, Scene(name="Edit"), baseline),
        lambda: clear_recovery(project, baseline),
    ):
        with pytest.raises((OSError, ValueError)):
            operation()
    assert target.read_bytes() == b"keep"
    assert path.exists()


@pytest.mark.parametrize("operation", ["write", "clear"])
def test_observed_recovery_change_is_preserved(tmp_path, monkeypatch, operation):
    from solar_forge_engine.project import recovery

    baseline = Scene()
    project = create_project(tmp_path / "Game", baseline)
    write_recovery(project, Scene(name="First edit"), baseline)
    path = recovery_path(project)
    real_read = recovery._read_snapshot
    calls = 0

    def changed(project):
        nonlocal calls
        calls += 1
        if calls == 2:
            path.write_bytes(b"changed by another editor")
        return real_read(project)

    monkeypatch.setattr(recovery, "_read_snapshot", changed)
    with pytest.raises(ValueError, match="changed during"):
        if operation == "write":
            write_recovery(project, Scene(name="Second edit"), baseline)
        else:
            recovery.clear_recovery(project, baseline)
    assert path.read_bytes() == b"changed by another editor"


def test_recovery_cleanup_runs_in_worker_and_stays_with_original_scene(
    qtbot, tmp_path, monkeypatch
):
    from solar_forge_engine.project.recovery import clear_recovery

    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor._confirm_discard = lambda: True
    editor.add_rectangle()
    assert editor.create_workspace(tmp_path / "Game")
    project = editor.project
    baseline = editor.saved_scene
    write_recovery(project, replace(baseline, name="Recovery"), baseline)
    started, proceed = Event(), Event()

    def delayed(*args):
        started.set()
        assert proceed.wait(3)
        clear_recovery(*args)

    monkeypatch.setattr("solar_forge_engine.editor.recovery.clear_recovery", delayed)
    assert editor.save()
    qtbot.waitUntil(started.is_set)
    try:
        editor.new_scene()
        editor.add_rectangle()
        new_scene = editor.document.scene
        assert editor.project is None
        assert recovery_path(project).exists()
    finally:
        proceed.set()
    qtbot.waitUntil(lambda: editor._recovery_job is None)
    assert not recovery_path(project).exists()
    assert editor.document.scene == new_scene
