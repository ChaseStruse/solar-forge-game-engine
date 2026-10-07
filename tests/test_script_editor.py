from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor

from solar_forge_engine.core.commands import SetSceneName
from solar_forge_engine.core.scene import Scene
from solar_forge_engine.editor.scripts import CodeEdit, ScriptDialog
from solar_forge_engine.editor.window import EditorWindow


def test_native_editor_applies_one_undoable_source_edit_without_running_it(
    qtbot, monkeypatch, tmp_path
):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    marker = tmp_path / "not-executed"
    source = f"open({str(marker)!r}, 'w').close()\n"

    def edit(dialog):
        dialog.code.setPlainText(source)
        dialog.apply_button.click()
        return dialog.result()

    monkeypatch.setattr(ScriptDialog, "exec", edit)
    editor.edit_script()
    assert editor.document.scene.script == source
    assert editor.document.revision == 1 and editor.dirty
    editor.undo()
    assert editor.document.scene.script == ""
    editor.redo()
    assert editor.document.scene.script == source
    assert not marker.exists()
    editor._confirm_discard = lambda: True
    editor.close()


def test_stale_script_draft_is_retained_and_cancel_does_not_mutate_scene(qtbot, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)

    def edit(dialog):
        dialog.code.setPlainText("# retain this draft")
        editor.execute(SetSceneName("Changed while editing"))
        dialog.apply_button.click()
        assert "scene changed" in dialog.status.text()
        assert dialog.code.toPlainText() == "# retain this draft"
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(ScriptDialog, "exec", edit)
    editor.edit_script()
    assert editor.document.scene == Scene("Changed while editing")
    editor._confirm_discard = lambda: True
    editor.close()


def test_code_indentation_preserves_unicode_and_oversized_source_cannot_apply(qtbot):
    source = 'message = "🔥"\nprint(message)'
    code = CodeEdit(source)
    qtbot.addWidget(code)
    code.selectAll()
    qtbot.keyClick(code, Qt.Key.Key_Tab)
    assert code.toPlainText() == '    message = "🔥"\n    print(message)'
    qtbot.keyClick(code, Qt.Key.Key_Backtab)
    assert code.toPlainText() == source
    code.setPlainText("def on_start(game):")
    code.moveCursor(QTextCursor.MoveOperation.End)
    qtbot.keyClick(code, Qt.Key.Key_Return)
    assert code.toPlainText() == "def on_start(game):\n    "
    dialog = ScriptDialog(Scene(), None)
    qtbot.addWidget(dialog)
    dialog.code.setPlainText("x" * 32769)
    assert not dialog.apply_button.isEnabled()
