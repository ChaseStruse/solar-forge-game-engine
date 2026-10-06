import hashlib
import json
import os
import subprocess
import tarfile

import pytest

from solar_forge_engine.core.scene import Entity, Role, Scene
from solar_forge_engine.core.script import ScriptBinding
from solar_forge_engine.editor.window import EditorWindow
from solar_forge_engine.project.bundling import export_bundle


def bundle_scene():
    return Scene(
        "Portable courier",
        (Entity("player", role=Role.PLAYER), Entity("coin", x=64, role=Role.COIN)),
        scripts=(
            ScriptBinding.from_source(
                "player",
                "courier",
                "def start(ctx):\n    ctx.add_score(42)\n"
                "def update(ctx, dt):\n    ctx.move(240 * dt, 0)\n",
            ),
        ),
    )


def test_editor_exports_relocatable_scripted_bundle_without_editor_dependencies(qtbot, tmp_path):
    editor = EditorWindow()
    qtbot.addWidget(editor)
    scene = bundle_scene()
    editor._open_starter(scene, "Bundle fixture")
    archive = tmp_path / "Portable.tar.gz"
    assert editor.export_game_to(archive)
    qtbot.waitUntil(lambda: editor._export_job is None, timeout=120000)
    assert archive.is_file(), editor.log.toPlainText()
    assert "Includes Python and Qt" in editor.log.toPlainText()
    assert editor.document.scene == scene and editor.dirty
    destination = tmp_path / "Moved game"
    destination.mkdir()
    with tarfile.open(archive) as package:
        members = package.getmembers()
        assert all(member.isfile() and not member.issym() for member in members)
        assert all(member.name.startswith("Game/") for member in members)
        package.extractall(destination, filter="data")
    root = destination / "Game"
    manifest = json.loads((root / "bundle.json").read_text())
    for entry in manifest["files"]:
        assert hashlib.sha256((root / entry["path"]).read_bytes()).hexdigest() == entry["sha256"]
    site = root / "runtime/lib/python3.14/site-packages"
    assert {path.name for path in site.iterdir()} == {"PySide6", "shiboken6"}
    assert not any(
        "qml" in str(path).casefold() or "quick" in str(path).casefold() for path in site.rglob("*")
    )
    assert not list(root.rglob("*.pyc"))
    assert (root / "notices/qtbase.txt").stat().st_size > 0
    assert (root / "notices/cpython.txt").stat().st_size > 0
    environment = dict(
        os.environ, PATH="/usr/bin:/bin", PYTHONHOME="/missing-python", PYTHONPATH=str(tmp_path)
    )
    (tmp_path / "solar_forge_engine.py").write_text("raise RuntimeError('project import executed')")
    result = subprocess.run(
        [str(root / "Play"), "--check-runtime", "--json"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(result.stdout)["ready"]
    result = subprocess.run(
        [str(root / "Play"), "--smoke-check"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["scripts_ready"] and not report["script_failed"]
    assert report["runtime_from_archive"] and not report["editor_loaded"]
    assert report["score"] == 42 and report["collected"] == 1 and report["x"] > 0
    editor._confirm_discard = lambda: True
    editor.close()


def test_bundle_rejects_existing_targets_links_and_empty_games_without_partial_output(tmp_path):
    target = tmp_path / "Existing.tar.gz"
    target.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        export_bundle(target, bundle_scene())
    assert target.read_bytes() == b"existing"
    link = tmp_path / "Link.tar.gz"
    link.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic"):
        export_bundle(link, bundle_scene())
    empty = tmp_path / "Empty.tar.gz"
    with pytest.raises(ValueError, match="Add an object"):
        export_bundle(empty, Scene())
    assert not empty.exists()


def test_python_bundle_refuses_links_and_skips_unrelated_installation_files(tmp_path, monkeypatch):
    import sys

    from solar_forge_engine.project import bundling

    base = tmp_path / "python"
    library = base / "lib/python3.14"
    library.mkdir(parents=True)
    (base / "bin").mkdir()
    executable = base / "bin/python3.14"
    executable.write_bytes(b"trusted interpreter fixture")
    (library / "LICENSE.txt").write_text("Python license fixture")
    (library / "os.py").write_text("# standard library fixture")
    (library / ".env").write_text("must not be bundled")
    (library / "site-packages").mkdir()
    (library / "site-packages/editor.py").write_text("must not be bundled")
    monkeypatch.setattr(sys, "base_prefix", str(base))
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(bundling.sysconfig, "get_path", lambda name: str(library))
    monkeypatch.setattr(bundling, "python_dependencies", lambda *args: ({}, []))
    destination = tmp_path / "safe"
    bundling._copy_python(destination)
    assert (destination / "runtime/lib/python3.14/os.py").is_file()
    assert not list(destination.rglob(".env"))
    assert not list(destination.rglob("editor.py"))
    private = tmp_path / "private.py"
    private.write_text("must not be bundled")
    (library / "private.py").symlink_to(private)
    with pytest.raises(ValueError, match="symbolic link"):
        bundling._copy_python(tmp_path / "unsafe")
