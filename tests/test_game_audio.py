from dataclasses import asdict

from PySide6.QtCore import QTimer
from test_audio import fake_player, sound_project, wait_scan
from test_scene_audio import clip

from solar_forge_engine.core.commands import SetCoinSound
from solar_forge_engine.core.scene import Entity, Role, Scene
from solar_forge_engine.editor.audio import SoundsDialog
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.audio import import_wav, load_clip
from solar_forge_engine.project.workspace import open_project
from solar_forge_engine.runtime.player import PlayerWindow


def test_editor_assigns_removes_and_undoes_reviewed_sound(tmp_path, qtbot, monkeypatch):
    project, source = sound_project(tmp_path)
    sound = import_wav(project, source)
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(project.root)
    expected = load_clip(project.root, sound.reference)
    actual_exec = SoundsDialog.exec

    def choose(dialog):
        def select():
            if dialog._job is not None:
                QTimer.singleShot(10, select)
            else:
                dialog.files.setCurrentRow(0)
                dialog.choose_sound()

        QTimer.singleShot(0, select)
        return actual_exec(dialog)

    monkeypatch.setattr(SoundsDialog, "exec", choose)
    editor.browse_sounds()
    assert editor.document.scene.coin_sound == expected
    assert editor.clear_sound_action.isEnabled()
    assert editor.save()
    assert open_project(project.root)[1].coin_sound == expected
    editor.clear_sound_action.trigger()
    assert editor.document.scene.coin_sound is None
    editor.undo()
    assert editor.document.scene.coin_sound == expected
    editor.redo()
    assert editor.document.scene.coin_sound is None
    editor.undo()
    assert not editor.dirty
    editor.close()


def test_stale_sound_assignment_is_rejected_without_losing_current_scene(
    tmp_path, qtbot, monkeypatch
):
    project, source = sound_project(tmp_path)
    sound = import_wav(project, source)
    editor = EditorWindow()
    qtbot.addWidget(editor)
    assert editor.load_workspace(project.root)
    errors = []
    monkeypatch.setattr(editor, "_error", errors.append)

    def stale(dialog):
        wait_scan(qtbot, dialog)
        editor.execute(SetCoinSound(asdict(clip())))
        dialog.sound_changed = True
        dialog.chosen_clip = load_clip(project.root, sound.reference)
        return 1

    monkeypatch.setattr(SoundsDialog, "exec", stale)
    editor.browse_sounds()
    assert errors and "scene changed" in errors[-1]
    assert editor.document.revision == 1
    assert editor.document.scene.coin_sound == clip()
    editor.undo()
    editor.close()


def test_collections_trigger_once_and_pause_restart_close_dispose_voice(
    tmp_path, qtbot, monkeypatch
):
    captured = tmp_path / "samples"
    fake_player(
        tmp_path,
        monkeypatch,
        f"import sys, time\nfrom pathlib import Path\n"
        f"Path({str(captured)!r}).write_bytes(sys.stdin.buffer.read())\ntime.sleep(30)",
    )
    authored = Scene(
        entities=(Entity("player", role=Role.PLAYER), Entity("coin", role=Role.COIN)),
        coin_sound=clip(),
    )
    player = PlayerWindow(authored, "player")
    qtbot.addWidget(player)
    player.timer.stop()
    player.show()
    qtbot.waitUntil(player.isActiveWindow)
    player.simulation.step(0, 0)
    player._sync_position()
    qtbot.waitUntil(captured.exists)
    pid = player.sound_player.process.processId()
    assert pid > 0 and captured.read_bytes() == b"\0" * 1600
    player._sync_position()
    assert player.sound_player.process.processId() == pid
    player.toggle_pause()
    qtbot.waitUntil(lambda: not player.sound_player.active)
    captured.unlink()
    player.restart()
    player.timer.stop()
    assert player._audio_count == 0 and not player.simulation.collected
    player.simulation.step(0, 0)
    player._sync_position()
    qtbot.waitUntil(captured.exists)
    assert player.sound_player.process.processId() != pid
    player.close()
    qtbot.waitUntil(lambda: not player.sound_player.active and not player.isVisible())
    assert authored.coin_sound == clip()
    assert authored.entity("player").x == 0
