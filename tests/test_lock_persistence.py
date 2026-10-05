import json
import os
from threading import Event

import pytest
from test_preferences import editor

from solar_forge_engine.editor.locks import metadata_path, read_locks, write_locks
from solar_forge_engine.project.workspace import create_scene


def idle(qtbot, window):
    qtbot.waitUntil(lambda: not window.lock_preferences.busy)


def test_lock_roundtrip_scene_switch_save_as_and_game_bytes_unchanged(qtbot, tmp_path):
    window = editor(qtbot)
    window.new_collector()
    assert window.create_workspace(tmp_path / "game")
    idle(qtbot, window)
    scene_path = window.path
    original = scene_path.read_bytes()
    window.set_selected_lock(True)
    idle(qtbot, window)
    assert read_locks(metadata_path(scene_path))[0] == frozenset({"player"})
    assert scene_path.read_bytes() == original
    create_scene(window.project, "Other")
    assert window.switch_project_scene("scenes/Other.forge.json")
    idle(qtbot, window)
    assert not window.view.locked_ids
    assert window.switch_project_scene("scenes/main.forge.json")
    idle(qtbot, window)
    assert window.view.locked_ids == frozenset({"player"})
    reopened = editor(qtbot)
    assert reopened.load_workspace(tmp_path / "game")
    idle(qtbot, reopened)
    assert reopened.view.locked_ids == frozenset({"player"})
    reopened.unlock_all_action.trigger()
    idle(qtbot, reopened)
    assert not read_locks(metadata_path(scene_path))[0]
    window.path = tmp_path / "copy.forge.json"
    window.project = None
    assert window.save()
    idle(qtbot, window)
    assert read_locks(metadata_path(window.path))[0] == frozenset({"player"})


def test_loaded_locks_merge_edits_made_while_loading(qtbot, tmp_path, monkeypatch):
    window = editor(qtbot)
    window.new_collector()
    window.path = tmp_path / "scene.forge.json"
    assert window.save()
    idle(qtbot, window)
    path = metadata_path(window.path)
    write_locks(path, frozenset({"player"}), read_locks(path)[1])
    started, release = Event(), Event()
    real_read = read_locks

    def delayed(path):
        result = real_read(path)
        started.set()
        assert release.wait(3)
        return result

    monkeypatch.setattr("solar_forge_engine.editor.locks.read_locks", delayed)
    assert window.load(window.path)
    qtbot.waitUntil(started.is_set)
    wall = next(entity for entity in window.document.scene.entities if entity.role.value == "wall")
    window.selected_id = wall.id
    window.set_selected_lock(True)
    release.set()
    idle(qtbot, window)
    assert window.view.locked_ids == frozenset({"player", wall.id})
    assert real_read(path)[0] == window.view.locked_ids


def test_pending_locks_survive_rapid_scene_switch_and_close(qtbot, tmp_path, monkeypatch):
    window = editor(qtbot)
    window.new_collector()
    assert window.create_workspace(tmp_path / "game")
    idle(qtbot, window)
    path = metadata_path(window.path)
    create_scene(window.project, "Other")
    started, release = Event(), Event()
    real_read = read_locks

    def delayed(path):
        result = real_read(path)
        started.set()
        assert release.wait(3)
        return result

    monkeypatch.setattr("solar_forge_engine.editor.locks.read_locks", delayed)
    assert window.load_workspace(tmp_path / "game")
    qtbot.waitUntil(started.is_set)
    window.selected_id = "player"
    window.set_selected_lock(True)
    assert window.switch_project_scene("scenes/Other.forge.json")
    assert window.switch_project_scene("scenes/main.forge.json")
    release.set()
    idle(qtbot, window)
    assert window.view.locked_ids == frozenset({"player"})
    window.unlock_all_action.trigger()
    assert window.close()
    assert not real_read(path)[0]


def test_corrupt_and_externally_changed_metadata_are_preserved(qtbot, tmp_path):
    window = editor(qtbot)
    window.new_collector()
    window.path = tmp_path / "scene.forge.json"
    assert window.save()
    idle(qtbot, window)
    path = metadata_path(window.path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"{bad")
    assert window.load(window.path)
    idle(qtbot, window)
    window.selected_id = "player"
    window.set_selected_lock(True)
    idle(qtbot, window)
    assert path.read_bytes() == b"{bad"
    assert window.view.locked_ids == frozenset({"player"})
    assert "persistence failed" in window.log.toPlainText()
    path.unlink()
    raw = write_locks(path, frozenset(), None)
    path.write_bytes(json.dumps({"format_version": 1, "locked_ids": ["player"]}).encode())
    changed = path.read_bytes()
    with pytest.raises(ValueError, match="externally"):
        write_locks(path, frozenset({"other"}), raw)
    assert path.read_bytes() == changed


def test_metadata_resource_bounds_regular_files_and_symlinks(tmp_path):
    path = tmp_path / "locks.json"
    for raw in (
        b"x" * (1024 * 1024 + 1),
        b'{"format_version":true,"locked_ids":[]}',
        b'{"format_version":1,"locked_ids":["../bad"]}',
        b'{"format_version":1,"locked_ids":["x","x"]}',
    ):
        path.write_bytes(raw)
        with pytest.raises(ValueError):
            read_locks(path)
        assert path.read_bytes() == raw
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(OSError):
        read_locks(link)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular"):
        read_locks(fifo)
