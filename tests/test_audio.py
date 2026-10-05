import io
import os
import shutil
import sys
import wave

import pytest
from PySide6.QtCore import QProcess

from solar_forge_engine.core.scene import Scene
from solar_forge_engine.editor import audio as audio_ui
from solar_forge_engine.editor.audio import SoundsDialog
from solar_forge_engine.project import audio
from solar_forge_engine.project.audio import decode_wav, import_wav, list_sounds, load_sound
from solar_forge_engine.project.workspace import create_project, open_project


def wav_bytes(*, frames=800, rate=8000, channels=1, width=2):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setparams((channels, width, rate, frames, "NONE", ""))
        handle.writeframes(b"\0" * frames * channels * width)
    return buffer.getvalue()


def sound_project(tmp_path):
    project = create_project(tmp_path / "Game", Scene())
    source = tmp_path / "Solar Chime.wav"
    source.write_bytes(wav_bytes())
    return project, source


def test_import_is_deduplicated_portable_and_preserves_scene(tmp_path):
    project, source = sound_project(tmp_path)
    before = project.scene_path().read_bytes()
    sound = import_wav(project, source)
    assert sound.name == "solar chime"
    assert sound.duration == 0.1
    source.rename(tmp_path / "Other name.wav")
    assert import_wav(project, tmp_path / "Other name.wav") == sound
    assert list_sounds(project) == (sound,)
    assert project.scene_path().read_bytes() == before
    copy = tmp_path / "Moved"
    shutil.copytree(project.root, copy)
    moved, scene = open_project(copy)
    assert scene == Scene()
    assert load_sound(moved, sound.reference) == (sound, b"\0" * 1600)


@pytest.mark.parametrize(
    "raw",
    [
        b"not a wave",
        wav_bytes()[:-1],
        wav_bytes(rate=96000),
        wav_bytes(channels=3),
        wav_bytes(width=3),
        wav_bytes(frames=0),
        wav_bytes(frames=8000 * 30 + 1),
    ],
)
def test_invalid_wav_does_not_publish(tmp_path, raw):
    project, source = sound_project(tmp_path)
    source.write_bytes(raw)
    with pytest.raises(ValueError):
        import_wav(project, source)
    assert not (project.root / "audio").exists()


def test_unsafe_and_changed_sound_files_are_preserved(tmp_path):
    project, source = sound_project(tmp_path)
    link = tmp_path / "link.wav"
    link.symlink_to(source)
    with pytest.raises(OSError):
        import_wav(project, link)
    fifo = tmp_path / "fifo.wav"
    os.mkfifo(fifo)
    with pytest.raises(ValueError, match="regular"):
        import_wav(project, fifo)
    sound = import_wav(project, source)
    target = project.root / sound.reference
    target.write_bytes(wav_bytes(frames=400))
    before = target.read_bytes()
    with pytest.raises(ValueError, match="fingerprint"):
        import_wav(project, source)
    assert target.read_bytes() == before
    with pytest.raises(ValueError, match="reference"):
        load_sound(project, "audio/../../elsewhere.wav")
    target.unlink()
    target.symlink_to(source)
    with pytest.raises(ValueError, match="Unexpected"):
        list_sounds(project)
    shutil.rmtree(project.root / "audio")
    outside = tmp_path / "outside"
    outside.mkdir()
    (project.root / "audio").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="regular audio directory"):
        import_wav(project, source)
    assert not list(outside.iterdir())


def test_sound_and_library_bounds(tmp_path, monkeypatch):
    project, source = sound_project(tmp_path)
    monkeypatch.setattr(audio, "MAX_SOUND_BYTES", 20)
    with pytest.raises(ValueError, match="4 MiB"):
        import_wav(project, source)
    with pytest.raises(ValueError, match="4 MiB"):
        decode_wav(source.read_bytes())
    monkeypatch.setattr(audio, "MAX_SOUND_BYTES", 4 * 1024 * 1024)
    sound = import_wav(project, source)
    monkeypatch.setattr(audio, "MAX_SOUNDS", 1)
    assert import_wav(project, source) == sound
    source.write_bytes(wav_bytes(frames=400))
    with pytest.raises(ValueError, match="128"):
        import_wav(project, source)
    monkeypatch.setattr(audio, "MAX_SOUNDS", 128)
    monkeypatch.setattr(audio, "MAX_LIBRARY_BYTES", 1800)
    with pytest.raises(ValueError, match="32 MiB"):
        import_wav(project, source)
    assert len(list_sounds(project)) == 1


def fake_player(tmp_path, monkeypatch, body, *, raw_option=True):
    program = tmp_path / "player"
    program.write_text(
        f"#!{sys.executable}\nimport sys\n"
        f"if '--help' in sys.argv:\n    print({'--raw' if raw_option else 'old-client'!r})\n"
        f"    sys.exit(0)\n{body}\n"
    )
    program.chmod(0o700)
    monkeypatch.setattr(audio_ui, "PIPEWIRE_PLAYER", str(program))


def wait_scan(qtbot, dialog):
    qtbot.waitUntil(lambda: dialog._job is None)


@pytest.mark.parametrize("raw_option", [False, True])
def test_dialog_import_preview_sends_only_pcm_and_reports_missing_backend(
    tmp_path, qtbot, monkeypatch, raw_option
):
    project, source = sound_project(tmp_path)
    captured = tmp_path / "captured.pcm"
    fake_player(
        tmp_path,
        monkeypatch,
        f"import sys\nfrom pathlib import Path\n"
        f"Path({str(captured)!r}).write_bytes(sys.stdin.buffer.read())",
        raw_option=raw_option,
    )
    dialog = SoundsDialog(project)
    qtbot.addWidget(dialog)
    dialog.show()
    wait_scan(qtbot, dialog)
    dialog._start("import", str(source))
    wait_scan(qtbot, dialog)
    assert dialog.files.currentRow() == 0
    assert dialog.preview_button.isEnabled()
    dialog.preview()
    qtbot.waitUntil(lambda: dialog.status.text() == "Preview finished.")
    assert captured.read_bytes() == b"\0" * 1600
    assert dialog.process.arguments()[-1] == "-"
    assert ("--raw" in dialog.process.arguments()) == raw_option
    monkeypatch.setattr(audio_ui, "PIPEWIRE_PLAYER", str(tmp_path / "missing-player"))
    dialog.preview()
    qtbot.waitUntil(lambda: "Preview unavailable" in dialog.status.text())
    assert dialog.preview_button.isEnabled()
    dialog.reject()


def test_closing_preview_kills_unresponsive_player(tmp_path, qtbot, monkeypatch):
    project, source = sound_project(tmp_path)
    import_wav(project, source)
    ready = tmp_path / "ready"
    fake_player(
        tmp_path,
        monkeypatch,
        f"import signal, time\nfrom pathlib import Path\n"
        f"signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"Path({str(ready)!r}).touch()\ntime.sleep(30)",
    )
    dialog = SoundsDialog(project)
    qtbot.addWidget(dialog)
    dialog.show()
    wait_scan(qtbot, dialog)
    dialog.files.setCurrentRow(0)
    dialog.preview()
    qtbot.waitUntil(ready.exists)
    dialog.reject()
    qtbot.waitUntil(lambda: dialog.process.state() == QProcess.ProcessState.NotRunning)
    qtbot.waitUntil(lambda: not dialog.isVisible())
    assert dialog.status.text() == "Preview stopped."
