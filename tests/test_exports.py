import io
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from test_animation import sheet
from test_scene_audio import clip

from solar_forge_engine.core.animation import Animation
from solar_forge_engine.core.commands import SetSceneName
from solar_forge_engine.core.scene import Entity, Role, Scene
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project import exporting
from solar_forge_engine.project.exporting import export_game

INPUT_SCRIPT = """
def on_start(game):
    assert game.actions["dash"] == {"held": False, "pressed": False, "released": False}
    game.data["presses"] = 0
    game.data["releases"] = 0
    game.data["held"] = False
    game.set_speed(360)
    game.say("Waiting for dash input")

def on_update(game, dt):
    dash = game.actions["dash"]
    game.data["presses"] += int(dash["pressed"])
    game.data["releases"] += int(dash["released"])
    game.data["held"] |= dash["held"]
    if game.data["presses"] and game.data["releases"] and game.data["held"]:
        assert game.data["presses"] == game.data["releases"] == 1
        game.say("Dash input verified")
"""


def game():
    return Scene(
        "Solar expedition",
        (
            Entity("player", role=Role.PLAYER, sprite=sheet(), animation=Animation(2, 1, 10)),
            Entity("coin", x=64, role=Role.COIN),
        ),
        coin_sound=clip(),
    )


def test_native_archive_runs_own_runtime_and_ignores_project_imports(tmp_path):
    scene = game()
    archive = tmp_path / "Expedition.pyz"
    size = export_game(archive, scene)
    assert size == archive.stat().st_size and os.access(archive, os.X_OK)
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        assert b"MIT License" in bundle.read("solar_forge_engine/LICENSE.txt")
        assert not any(part in name for name in names for part in ("/editor/", "/ai/", "/project/"))
        snapshot = json.loads(bundle.read("game_data/scene.json"))
        assert snapshot["scene"] == scene.to_data()
    untrusted = tmp_path / "Project"
    untrusted.mkdir()
    marker = tmp_path / "must-not-exist"
    (untrusted / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\n"
    )
    (untrusted / "solar_forge_engine.py").write_text("raise RuntimeError('project code executed')")
    environment = dict(os.environ, PYTHONPATH=str(untrusted), PYTHONHOME="/missing-python-home")
    environment["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
    )
    result = subprocess.run(
        [str(archive), "--smoke-check"],
        cwd=untrusted,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["runtime_from_archive"] and not report["editor_loaded"]
    assert report["scene_unchanged"] and report["collected"] == 1 and report["x"] > 0
    assert not marker.exists()
    assert scene == game()


def test_export_preserves_existing_targets_and_rejects_invalid_games(tmp_path, monkeypatch):
    target = tmp_path / "Game.pyz"
    target.write_bytes(b"existing game")
    with pytest.raises(FileExistsError):
        export_game(target, game())
    assert target.read_bytes() == b"existing game"
    link = tmp_path / "Link.pyz"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic"):
        export_game(link, game())
    assert target.read_bytes() == b"existing game"
    with pytest.raises(ValueError, match="Add an object"):
        export_game(tmp_path / "Empty.pyz", Scene())
    with pytest.raises(ValueError, match="extension"):
        export_game(tmp_path / "Wrong.txt", game())
    monkeypatch.setattr(exporting, "MAX_FILE_BYTES", 100)
    with pytest.raises(ValueError, match="4 MiB"):
        export_game(tmp_path / "Large.pyz", game())
    assert not (tmp_path / "Large.pyz").exists()


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(format_version=True),
        lambda data: data.update(control="missing"),
        lambda data: data["scene"].update(coin_sound={"asset": "../../secret"}),
    ],
)
def test_exported_runtime_rejects_invalid_snapshot_before_play(tmp_path, mutation):
    archive = tmp_path / "Invalid.pyz"
    export_game(archive, game())
    with zipfile.ZipFile(archive) as bundle:
        entries = {name: bundle.read(name) for name in bundle.namelist()}
    snapshot = json.loads(entries["game_data/scene.json"])
    mutation(snapshot)
    entries["game_data/scene.json"] = json.dumps(snapshot).encode()
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, raw in entries.items():
            bundle.writestr(name, raw)
    result = subprocess.run(
        [sys.executable, "-I", str(archive), "--smoke-check"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "Cannot launch game" in result.stderr and not result.stdout


@pytest.mark.parametrize("extension", [".pyz", ".tar.gz"])
def test_editor_exports_snapshot_without_saving_or_losing_later_edits(tmp_path, qtbot, extension):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor._open_starter(game(), "Export fixture")
    snapshot = editor.document.scene
    saved = editor.saved_scene
    target = tmp_path / f"Game{extension}"
    assert editor.export_game_to(target)
    editor.execute(SetSceneName("Later edit"))
    qtbot.waitUntil(lambda: editor._export_job is None, timeout=20000)
    assert editor.saved_scene == saved and editor.dirty
    assert editor.document.scene == replace(snapshot, name="Later edit")
    if extension == ".tar.gz":
        with tarfile.open(target) as bundle:
            stream = bundle.extractfile("Game/Game.pyz")
            assert stream is not None
            raw = stream.read()
    else:
        raw = target.read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert json.loads(archive.read("game_data/scene.json"))["scene"] == snapshot.to_data()
    editor._confirm_discard = lambda: True
    editor.close()


def test_exported_script_runs_in_restricted_worker_without_editor(tmp_path):
    archive = tmp_path / "Scripted.pyz"
    export_game(archive, replace(game(), script=INPUT_SCRIPT))
    result = subprocess.run(
        [sys.executable, "-I", str(archive), "--smoke-check"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["script_ready"] and not report["script_failed"]
    assert report["script_message"] == "Dash input verified"
    assert report["player_speed"] == 360 and report["collected"] == 1, report
    assert report["scene_unchanged"] and not report["editor_loaded"]
