from dataclasses import asdict
from threading import Event

from PySide6.QtWidgets import QMessageBox

from solar_forge_engine.core.commands import SetScript
from solar_forge_engine.core.script import ScriptBinding
from solar_forge_engine.editor.scripts import SourceLoader
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.recovery import read_recovery
from solar_forge_engine.project.workspace import open_project


def editor_with_object(qtbot):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    editor._confirm_discard = lambda: True
    return editor


def test_python_drafts_survive_selection_save_reopen_and_undoable_bindings(qtbot, tmp_path):
    editor = editor_with_object(qtbot)
    first = editor.selected_id
    editor.scripts.use_template()
    source = editor.scripts.code.toPlainText()
    editor.add_rectangle()
    second = editor.selected_id
    editor.scripts.templates.setCurrentText("Patrol")
    editor.scripts.use_template()
    editor.selected_id = first
    editor.refresh()
    assert editor.scripts.code.toPlainText() == source
    assert editor.dirty and editor.scripts.pending
    assert editor.create_workspace(tmp_path / "Game")
    assert not editor.scripts.pending and not editor.dirty
    bindings = editor.document.scene.scripts
    assert {binding.entity_id for binding in bindings} == {first, second}
    assert all((editor.project.root / binding.path).is_file() for binding in bindings)
    assert open_project(editor.project.root)[1] == editor.document.scene
    editor.scripts.detach()
    assert len(editor.document.scene.scripts) == 1
    editor.document.undo()
    editor.refresh()
    assert editor.document.scene.scripts == bindings
    editor.duplicate_selected()
    duplicate = editor.selected_id
    assert duplicate not in (first, second)
    assert editor.document.scene.scripts[-1].entity_id == duplicate
    assert editor.document.scene.scripts[-1].source == source
    editor.delete_selected()
    assert all(binding.entity_id != duplicate for binding in editor.document.scene.scripts)
    editor.document.undo()
    editor.refresh()
    assert editor.document.scene.scripts[-1].entity_id == duplicate
    editor.close()


def test_invalid_or_stale_drafts_do_not_partially_apply_or_overwrite_source(qtbot):
    editor = editor_with_object(qtbot)
    errors = []
    editor.scripts.report = errors.append
    first = editor.selected_id
    editor.scripts.use_template()
    editor.add_rectangle()
    second = editor.selected_id
    editor.scripts.use_template()
    editor.scripts.name.setText("invalid name")
    assert not editor.scripts.flush()
    assert not editor.document.scene.scripts
    assert editor.scripts.pending
    editor.scripts.name.setText("valid")
    assert editor.scripts.flush()
    editor.selected_id = first
    editor.refresh()
    editor.scripts.code.appendPlainText("# my pending edit")
    draft = editor.scripts.code.toPlainText()
    external = ScriptBinding.from_source(
        first, "external", "def start(ctx):\n    ctx.add_score(1)\n"
    )
    editor.execute(SetScript(first, asdict(external)))
    assert not editor.scripts.flush()
    assert editor.scripts.code.toPlainText() == draft
    assert editor.document.scene.scripts[0] == external
    editor.document.undo()
    editor.refresh()
    assert editor.scripts.flush()
    assert editor.document.scene.scripts[0].source == draft
    assert editor.document.scene.scripts[1].entity_id == second
    assert errors
    editor.close()


def test_unapplied_code_is_recoverable_and_save_cancel_preserves_draft(
    qtbot, tmp_path, monkeypatch
):
    editor = editor_with_object(qtbot)
    assert editor.create_workspace(tmp_path / "Game")
    editor.scripts.use_template()
    source = editor.scripts.code.toPlainText()
    editor.autosave()
    qtbot.waitUntil(lambda: editor._recovery_job is None)
    recovered = read_recovery(editor.project, editor.saved_scene)
    assert recovered.scripts[0].source == source
    assert not editor.document.scene.scripts
    monkeypatch.setattr(QMessageBox, "question", lambda *_: QMessageBox.StandardButton.Cancel)
    del editor._confirm_discard
    assert not editor._confirm_discard()
    assert editor.scripts.code.toPlainText() == source
    assert editor.save()
    assert not editor.dirty and not editor.scripts.pending
    assert open_project(editor.project.root)[1].scripts[0].source == source
    editor.close()


def test_import_is_bounded_does_not_execute_and_preserves_newer_drafts(
    qtbot, tmp_path, monkeypatch
):
    editor = editor_with_object(qtbot)
    errors = []
    editor.scripts.report = errors.append
    marker = tmp_path / "must-not-exist"
    path = tmp_path / "motion.py"
    source = f"open({str(marker)!r}, 'w').write('bad')\ndef update(ctx, dt):\n    pass\n"
    path.write_text(source)
    assert editor.scripts.import_source(path)
    qtbot.waitUntil(lambda: editor.scripts.loader is None)
    assert editor.scripts.code.toPlainText() == source and not marker.exists()
    assert not editor.document.scene.scripts
    release = Event()
    original = SourceLoader.run

    def delayed(job):
        assert release.wait(2)
        original(job)

    monkeypatch.setattr(SourceLoader, "run", delayed)
    assert editor.scripts.import_source(path)
    editor.scripts.code.setPlainText("def start(ctx):\n    pass\n")
    release.set()
    qtbot.waitUntil(lambda: editor.scripts.loader is None)
    assert editor.scripts.code.toPlainText() == "def start(ctx):\n    pass\n"
    assert "draft changed" in errors[-1]
    path.write_bytes(b"x" * 65537)
    assert editor.scripts.import_source(path)
    qtbot.waitUntil(lambda: editor.scripts.loader is None)
    assert "64 KiB" in errors[-1]
    assert not marker.exists()
    editor.close()


def test_preview_errors_navigate_to_actual_source_and_reject_stale_locations(qtbot):
    editor = editor_with_object(qtbot)
    editor.scripts.code.setPlainText("def start(ctx):\n    raise ValueError('fixture failure')\n")
    editor.play()
    qtbot.waitUntil(lambda: editor.scripts.errors.count() == 1, timeout=6000)
    try:
        row = editor.scripts.errors.item(0)
        assert "fixture failure" in row.text()
        editor.scripts._open_error(row)
        assert editor.scripts.code.textCursor().blockNumber() == 1
        errors = []
        editor.scripts.report = errors.append
        editor.scripts.code.appendPlainText("# changed")
        editor.scripts._open_error(row)
        assert "older Play snapshot" in errors[-1]
    finally:
        editor._close_preview()
        editor.close()


def test_python_apply_stays_accessible_with_scrolled_source_in_small_window(qtbot):
    from PySide6.QtCore import Qt

    editor = editor_with_object(qtbot)
    editor.resize(900, 600)
    editor.show()
    editor.edit_python()
    editor.scripts.use_template()
    qtbot.waitUntil(lambda: not editor.scripts.apply_button.visibleRegion().isEmpty())
    editor.script_scroll.verticalScrollBar().setValue(
        editor.script_scroll.verticalScrollBar().maximum()
    )
    assert not editor.scripts.apply_button.visibleRegion().isEmpty()
    qtbot.mouseClick(editor.scripts.apply_button, Qt.MouseButton.LeftButton)
    assert editor.document.scene.scripts[0].source == editor.scripts.code.toPlainText()
    assert not editor.scripts.pending
    editor.close()
