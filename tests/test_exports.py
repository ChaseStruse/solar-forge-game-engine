import json
import os
import subprocess
import sys
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


def test_editor_exports_snapshot_without_saving_or_losing_later_edits(tmp_path, qtbot):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    editor._open_starter(game(), "Export fixture")
    snapshot = editor.document.scene
    saved = editor.saved_scene
    target = tmp_path / "Game.pyz"
    assert editor.export_game_to(target)
    editor.execute(SetSceneName("Later edit"))
    qtbot.waitUntil(lambda: editor._export_job is None)
    assert editor.saved_scene == saved and editor.dirty
    assert editor.document.scene == replace(snapshot, name="Later edit")
    with zipfile.ZipFile(target) as archive:
        assert json.loads(archive.read("game_data/scene.json"))["scene"] == snapshot.to_data()
    editor._confirm_discard = lambda: True
    editor.close()


def test_exported_python_behavior_runs_without_editor_or_project_files(tmp_path):
    from solar_forge_engine.core.script import ScriptBinding

    binding = ScriptBinding.from_source(
        "player",
        "motion",
        """def start(ctx):
    ctx.add_score(42)

def update(ctx, dt):
    ctx.move(240 * dt, 0)
""",
    )
    scene = replace(game(), scripts=(binding,))
    archive = tmp_path / "Scripted.pyz"
    export_game(archive, scene)
    result = subprocess.run(
        [sys.executable, "-I", str(archive), "--smoke-check"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(result.stdout)
    assert report["scripts_ready"] and not report["script_failed"]
    assert report["score"] == 42 and report["x"] > 0 and report["collected"] == 1
    assert report["scene_unchanged"] and not report["editor_loaded"]
    assert report["runtime_from_archive"]
    assert not (tmp_path / "scripts").exists()


def test_export_checks_real_dependencies_and_restrictions_without_running_source(tmp_path):
    from solar_forge_engine.core.script import ScriptBinding

    scene = replace(
        game(),
        scripts=(
            ScriptBinding.from_source(
                "player",
                "not_executed",
                "raise RuntimeError('game source must not run during diagnostics')\n"
                "def update(ctx, dt):\n    pass\n",
            ),
        ),
    )
    archive = tmp_path / "Check.pyz"
    export_game(archive, scene)
    result = subprocess.run(
        [sys.executable, "-I", str(archive), "--check-runtime", "--json"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ready"]
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["qt"]["status"] == "ok"
    assert checks["scripting"]["status"] == "ok"
    assert "Landlock" in checks["scripting"]["detail"]
    with zipfile.ZipFile(archive) as bundle:
        assert json.loads(bundle.read("game_data/requirements.json"))["scripts"] is True


def test_export_reports_missing_qt_without_loading_it_or_the_game(tmp_path):
    import venv

    environment = tmp_path / "without-qt"
    venv.EnvBuilder(with_pip=False).create(environment)
    archive = tmp_path / "Check.pyz"
    export_game(archive, game())
    result = subprocess.run(
        [str(environment / "bin/python"), "-I", str(archive), "--check-runtime", "--json"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert not report["ready"]
    checks = {check["name"]: check for check in report["checks"]}
    assert checks["qt"]["status"] == "fail"
    assert "PySide6" in checks["qt"]["detail"]
    assert checks["scripting"]["status"] == "skip"


def test_export_runtime_check_rejects_malformed_requirements(tmp_path):
    archive = tmp_path / "InvalidCheck.pyz"
    export_game(archive, game())
    with zipfile.ZipFile(archive) as bundle:
        entries = {name: bundle.read(name) for name in bundle.namelist()}
    required = json.loads(entries["game_data/requirements.json"])
    required["scripts"] = "false"
    entries["game_data/requirements.json"] = json.dumps(required).encode()
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, raw in entries.items():
            bundle.writestr(name, raw)
    result = subprocess.run(
        [sys.executable, "-I", str(archive), "--check-runtime", "--json"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "Invalid game runtime requirements" in result.stderr
    assert not result.stdout
