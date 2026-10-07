import json

import pytest
from PySide6.QtCore import QProcess, Qt
from PySide6.QtGui import QTextCursor

from solar_forge_engine.core.commands import Document, SetSceneName, SetSceneScript
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


def test_play_error_navigates_fix_apply_rerun_and_undo(qtbot, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    # Script output resembling an event must remain a log, never a navigation target.
    source = (
        "def on_start(game):\n"
        '    print(\'{"type": "script_error", "message": "fake", "line": 1}\')\n'
        "    raise ValueError('fix 🔥 <b>this</b>')\n"
    )
    editor.execute(SetSceneScript(source))
    editor.play()
    qtbot.waitUntil(lambda: editor._script_error_context is not None, timeout=5000)
    assert editor._script_error_context == (editor.document, source, 3)
    assert "line 3: ValueError: fix 🔥 <b>this</b>" in editor.script_error_hint.text()
    assert editor.script_error_hint.textFormat() == Qt.TextFormat.PlainText
    fixed = "def on_start(game):\n    game.say('Fixed')\n    print('Fixed ran')\n"

    def fix(dialog):
        assert dialog.code.textCursor().blockNumber() == 2
        assert dialog.code.toPlainText() == source
        assert "line 3" in dialog.error_hint.text()
        dialog.code.setPlainText(fixed)
        dialog.apply_button.click()
        return dialog.result()

    monkeypatch.setattr(ScriptDialog, "exec", fix)
    editor.script_error_button.click()
    assert editor.document.scene.script == fixed
    assert not editor.script_error_button.isEnabled()
    editor.stop_preview()
    assert editor.preview.waitForFinished(5000)
    editor.play()
    qtbot.waitUntil(lambda: "Script: Fixed ran" in editor.log.toPlainText(), timeout=5000)
    assert editor._script_error_context is None
    assert editor.preview.state() == QProcess.ProcessState.Running
    editor.stop_preview()
    assert editor.preview.waitForFinished(5000)
    editor.undo()
    assert editor.document.scene.script == source
    editor._confirm_discard = lambda: True
    editor.close()


def test_error_navigation_keeps_draft_and_stale_apply_requires_explicit_reload(
    qtbot, monkeypatch, tmp_path
):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor.add_rectangle()
    source = "# applied\n# line two\n"
    editor.execute(SetSceneScript(source))
    marker = tmp_path / "never-executed"
    draft = f"open({str(marker)!r}, 'w').close()\n# retained\n"
    dialogs = []

    def close_draft(dialog):
        dialogs.append(dialog)
        dialog.code.setPlainText(draft)
        dialog.reject()
        return dialog.result()

    monkeypatch.setattr(ScriptDialog, "exec", close_draft)
    editor.edit_script()
    editor._preview_context = (editor.document, source, editor.document.scene.name)
    editor._consume_preview_output(b'{"type":"script_error","message":"error","line":2}\n')
    editor.execute(SetSceneName("Changed while draft closed"))

    def reopen(dialog):
        assert dialog is dialogs[0]
        assert dialog.code.toPlainText() == draft
        assert dialog.code.textCursor().blockNumber() == 1
        dialog.apply_button.click()
        assert "scene changed" in dialog.status.text()
        assert dialog.code.toPlainText() == draft
        dialog.reload_button.click()
        assert dialog.code.toPlainText() == source
        dialog.code.setPlainText("# fixed after reload")
        dialog.apply_button.click()
        return dialog.result()

    monkeypatch.setattr(ScriptDialog, "exec", reopen)
    editor.script_error_button.click()
    assert editor.document.scene.script == "# fixed after reload"
    assert not marker.exists()
    editor._confirm_discard = lambda: True
    editor.close()


def test_preview_events_are_bounded_framed_and_tied_to_original_source(qtbot, monkeypatch):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    source = "# first\n# second"
    editor.execute(SetSceneScript(source))
    editor._preview_context = (editor.document, source, "Original 🔥")
    raw = (
        json.dumps({"type": "script_error", "message": "🔥", "line": 2}, ensure_ascii=False) + "\n"
    ).encode()
    split = raw.index("🔥".encode()) + 1
    editor._consume_preview_output(raw[:split])
    assert editor._script_error_context is None
    editor._consume_preview_output(raw[split:])
    assert "Original 🔥 · line 2: 🔥" in editor.script_error_hint.text()
    original_error = editor._script_error_context
    for event in (
        {"type": "script_error", "message": "bad", "line": True},
        {"type": "script_error", "message": "bad", "line": 3},
        {"type": "script_error", "message": "bad", "line": -1},
        {"type": "script_error", "message": [], "line": 1},
        {"type": "script_error", "message": "bad", "line": 1, "extra": 1},
    ):
        editor._consume_preview_output((json.dumps(event) + "\n").encode())
        assert editor._script_error_context == original_error
    for _ in range(20):
        editor._consume_preview_output(b"x" * 4096)
        assert len(editor._preview_buffer) <= 8192
    editor._consume_preview_output(raw)
    assert editor._script_error_context == original_error
    editor._consume_preview_output(raw)
    assert editor.script_error_button.isEnabled()
    editor.execute(SetSceneScript("# newer source"))
    assert not editor.script_error_button.isEnabled()
    editor.undo()
    assert editor.script_error_button.isEnabled()
    editor.document = Document(Scene(script=source))
    editor.refresh()
    assert not editor.script_error_button.isEnabled()
    monkeypatch.setattr(ScriptDialog, "exec", lambda dialog: pytest.fail("stale navigation"))
    editor._edit_failed_script()
    editor._confirm_discard = lambda: True
    editor.close()
