import base64
from pathlib import Path
from threading import Event

import pytest

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.core.sprite import Sprite
from solar_forge_engine.editor.quarantine import QuarantineDialog
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.assets import store_asset
from solar_forge_engine.project.cleanup import plan_cleanup, quarantine_assets, sprite_reference
from solar_forge_engine.project.quarantine import list_quarantined, purge_asset, restore_asset
from solar_forge_engine.project.workspace import create_project, open_project


def quarantined_project(tmp_path):
    project = create_project(tmp_path / "Game", Scene())
    sprite = Sprite(1, 1, base64.b64encode(bytes([30, 40, 50, 255])).decode())
    path = project.root / sprite_reference(sprite)
    store_asset(path, base64.b64decode(sprite.pixels))
    quarantine_assets(project, set(), plan_cleanup(project, set()))
    entry = list_quarantined(project)[0]
    return project, path, entry


def test_restore_preserves_bytes_scene_and_empty_batches(tmp_path):
    project, path, entry = quarantined_project(tmp_path)
    scene_bytes = project.scene_path().read_bytes()
    source = project.root / ".asset-quarantine" / entry.reference
    raw = source.read_bytes()
    restore_asset(project, entry)
    assert path.read_bytes() == raw
    assert not source.exists()
    assert not list_quarantined(project)
    assert project.scene_path().read_bytes() == scene_bytes
    assert open_project(project.root)[1] == Scene()


def test_purge_removes_only_reviewed_copy_and_preserves_scene(tmp_path):
    project, path, entry = quarantined_project(tmp_path)
    scene_bytes = project.scene_path().read_bytes()
    source = project.root / ".asset-quarantine" / entry.reference
    path.write_bytes(source.read_bytes())
    raw = path.read_bytes()
    purge_asset(project, entry)
    assert not source.exists()
    assert path.read_bytes() == raw
    assert project.scene_path().read_bytes() == scene_bytes
    assert not list_quarantined(project)


@pytest.mark.parametrize("failure", ["changed", "symlink", "missing", "unlink"])
def test_purge_revalidation_or_unlink_failure_preserves_other_files(tmp_path, monkeypatch, failure):
    project, path, entry = quarantined_project(tmp_path)
    source = project.root / ".asset-quarantine" / entry.reference
    path.write_bytes(b"keep")
    if failure == "changed":
        source.write_bytes(b"edit")
    elif failure == "symlink":
        source.unlink()
        source.symlink_to(path)
    elif failure == "missing":
        source.unlink()
    else:
        unlink = Path.unlink

        def refuse(self, *args, **kwargs):
            if self == source:
                raise OSError("unlink failed")
            return unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", refuse)
    with pytest.raises((ValueError, OSError)):
        purge_asset(project, entry)
    assert path.read_bytes() == b"keep"
    if failure != "missing":
        assert source.exists()


def test_browser_purge_cancellation_and_confirmation(qtbot, tmp_path, monkeypatch):
    project, _, entry = quarantined_project(tmp_path)
    source = project.root / ".asset-quarantine" / entry.reference
    dialog = QuarantineDialog(project)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog._job is None)
    dialog.files.setCurrentRow(0)
    monkeypatch.setattr(dialog, "_confirm_purge", lambda asset: False)
    dialog.review_purge()
    qtbot.waitUntil(lambda: dialog._job is None)
    assert source.exists()
    assert not dialog.purged
    assert "cancelled" in dialog.status.text()
    monkeypatch.setattr(dialog, "_confirm_purge", lambda asset: True)
    dialog.review_purge()
    qtbot.waitUntil(lambda: dialog._job is None)
    assert not source.exists()
    assert dialog.purged
    assert not dialog.files.count()
    assert not dialog.purge_button.isEnabled()


def test_browser_rechecks_file_after_confirmation(qtbot, tmp_path, monkeypatch):
    project, _, entry = quarantined_project(tmp_path)
    source = project.root / ".asset-quarantine" / entry.reference
    dialog = QuarantineDialog(project)
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog._job is None)
    dialog.files.setCurrentRow(0)

    def confirm(asset):
        source.write_bytes(b"edit")
        return True

    monkeypatch.setattr(dialog, "_confirm_purge", confirm)
    dialog.review_purge()
    qtbot.waitUntil(lambda: dialog._job is None)
    assert source.read_bytes() == b"edit"
    assert not dialog.purged
    assert "changed after review" in dialog.status.text()


@pytest.mark.parametrize("conflict", ["existing", "symlink", "changed", "assets_link"])
def test_restore_conflicts_leave_quarantined_bytes_available(tmp_path, conflict):
    project, path, entry = quarantined_project(tmp_path)
    source = project.root / ".asset-quarantine" / entry.reference
    if conflict == "existing":
        path.write_bytes(b"existing")
    elif conflict == "symlink":
        path.symlink_to(tmp_path / "missing")
    elif conflict == "changed":
        source.write_bytes(b"edit")
    else:
        path.parent.rmdir()
        path.parent.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises((ValueError, OSError)):
        restore_asset(project, entry)
    assert source.exists()
    if conflict == "existing":
        assert path.read_bytes() == b"existing"
    elif conflict == "symlink":
        assert path.is_symlink()
        assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("failure", ["batch_link", "unknown", "budget"])
def test_browser_refuses_incomplete_or_unsafe_scans(tmp_path, monkeypatch, failure):
    project, path, entry = quarantined_project(tmp_path)
    folder = project.root / ".asset-quarantine"
    if failure == "batch_link":
        (folder / ("f" * 32)).symlink_to(tmp_path, target_is_directory=True)
    elif failure == "unknown":
        (folder / "notes.txt").write_text("retained")
    else:
        monkeypatch.setattr("solar_forge_engine.project.quarantine.MAX_SCAN_BYTES", 1)
    with pytest.raises(ValueError):
        list_quarantined(project)
    assert (folder / entry.reference).exists()
    assert not path.exists()


def test_failed_quarantine_unlink_retains_both_copies(tmp_path, monkeypatch):
    project, path, entry = quarantined_project(tmp_path)
    source = project.root / ".asset-quarantine" / entry.reference
    unlink = Path.unlink

    def fail_source(self, *args, **kwargs):
        if self == source:
            raise OSError("unlink failed")
        return unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_source)
    with pytest.raises(OSError, match="unlink failed"):
        restore_asset(project, entry)
    assert source.read_bytes() == path.read_bytes()


def test_native_browser_restores_selected_file_without_editing_scene(qtbot, tmp_path, monkeypatch):
    project, path, entry = quarantined_project(tmp_path)
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(project.root)
    qtbot.waitUntil(lambda: editor._asset_index_job is None)
    original, revision = editor.document.scene, editor.document.revision

    def interact(dialog):
        qtbot.addWidget(dialog)
        qtbot.waitUntil(lambda: dialog._job is None)
        assert dialog.files.count() == 1
        assert entry.reference in dialog.files.item(0).text()
        dialog.files.setCurrentRow(0)
        assert dialog.restore_button.isEnabled()
        dialog.restore_selected()
        qtbot.waitUntil(lambda: dialog._job is None)
        assert dialog.restored
        assert dialog.files.count() == 0
        assert "restored" in dialog.status.text()
        return 0

    monkeypatch.setattr(QuarantineDialog, "exec", interact)
    editor.browse_quarantine()
    qtbot.waitUntil(lambda: editor._asset_index_job is None)
    assert path.exists()
    assert editor.document.scene == original
    assert editor.document.revision == revision
    assert not editor.dirty


def test_browser_does_not_close_during_worker_and_keeps_conflict_visible(
    qtbot, tmp_path, monkeypatch
):
    project, path, entry = quarantined_project(tmp_path)
    started, proceed = Event(), Event()
    scan = list_quarantined

    def delayed_scan(project):
        started.set()
        assert proceed.wait(3)
        return scan(project)

    monkeypatch.setattr("solar_forge_engine.editor.quarantine.list_quarantined", delayed_scan)
    dialog = QuarantineDialog(project)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(started.is_set)
    try:
        dialog.reject()
        assert dialog.isVisible()
    finally:
        proceed.set()
    qtbot.waitUntil(lambda: dialog._job is None)
    path.write_bytes(b"existing")
    dialog.files.setCurrentRow(0)
    dialog.restore_selected()
    qtbot.waitUntil(lambda: dialog._job is None)
    assert "Operation stopped" in dialog.status.text()
    assert dialog.files.count() == 1
    assert not dialog.restored
    assert path.read_bytes() == b"existing"
    assert (project.root / ".asset-quarantine" / entry.reference).exists()
